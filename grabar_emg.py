"""Graba la señal cruda de EMG que manda la ESP32-C3 por BLE y la guarda en un CSV.

Uso:
    pip install bleak matplotlib
    python grabar_emg.py salida.csv 60      # graba 60 segundos

Al terminar muestra un grafico de la señal grabada.
"""

import asyncio #libreria que sirve para programas que esperen cosas sin quedarse bloqueados
import csv
import struct
import sys
from bleak import BleakClient, BleakScanner

DEVICE_NAME="MyoSignals"
EMG_UUID = "8d1f0002-6c3a-4b8e-9a2e-3f1b2c4d5e60"
FS=2000
BLOCK= 100 #muestras x paquete


async def grabar(path,duracion):
    print(f"Buscando {DEVICE_NAME}...")
    dev = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=15)
    if dev is None:
        print("No se encontró el dispositivo por nombre exacto; revisando dispositivos visibles...")
        try:
            devices = await BleakScanner.discover(timeout=10)
        except Exception as exc:
            print(f"No pude escanear BLE: {exc}")
            return None

        if devices:
            for d in devices:
                nombre = d.name or "<sin nombre>"
                print(f"- {nombre} ({d.address})")

        dev = next(
            (d for d in devices if d.name and DEVICE_NAME.lower() in d.name.lower()),
            None,
        )

        if dev is None:
            print("No se encontró ningun dispositivo compatible.")
            return None

    estado = {"n":0, "last": None, "perdidos":0, "paquetes":0} 
    # n: cuantas muestras van
    # last: numero de secuencia del ultimo paquete recibido. Sirve para detectar si se saltó alguno. 
    #perdidos: cuantos paquetes se perdieron
    #cuantos paquetes lleegaron bien 
    t_all, v_all=[], [] #listas donde el script va guardando todos los datos que llegan
    f = open(path, "w", newline="")
    w = csv.writer(f) #crea un escritor de CSV sobre ese archivo
    w.writerow(["muestra", "t_s", "mV"]) #

    def on_data(_, data: bytearray): #on data: función de bleak que llama cada vez q le llega un paquete de la ESP. 
    #Recibe el paquete, lo decodifica, revisa si se perdió alguno y guarda las muestras.
        seq = struct.unpack_from("<H",data,0)[0]
        k=(len(data)-2)//2
        muestras = struct.unpack_from(f"<{k}H", data, 2)
        if estado["last"] is not None:
            salto = (seq - estado["last"] - 1) & 0xFFFF
            if salto:
                # se perdieron paquetes: se avanza el tiempo para no deformar el eje
                estado["perdidos"] += salto
                estado["n"] += salto * BLOCK
        estado["last"] = seq
        estado["paquetes"] += 1
        for mv in muestras:
            t = estado["n"] / FS
            w.writerow([estado["n"], f"{t:.4f}", mv])
            t_all.append(t)
            v_all.append(mv)
            estado["n"] += 1

    async with BleakClient(dev) as client:
        print(f"Conectado. MTU = {client.mtu_size}")
        if client.mtu_size < 2 + 2 * BLOCK + 3:
             print("Atencion: MTU chico, los paquetes pueden llegar cortados.")
        await client.start_notify(EMG_UUID, on_data)
        print(f"Grabando {duracion} s...")
        await asyncio.sleep(duracion)
        await client.stop_notify(EMG_UUID)

    f.close()
    total = estado["paquetes"] + estado["perdidos"]
    print(f"Listo: {estado['paquetes']} paquetes recibidos, {estado['perdidos']} perdidos "
          f"({100 * estado['perdidos'] / max(total, 1):.1f} %). Guardado en {path}")
    return t_all, v_all


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "emg.csv"
    duracion = float(sys.argv[2]) if len(sys.argv) > 2 else 30
    res = asyncio.run(grabar(path, duracion))
    if not res or not res[0]:
        return
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    t, v = res
    plt.figure(figsize=(12, 4))
    plt.plot(t, v, lw=0.5)
    plt.xlabel("Tiempo [s]")
    plt.ylabel("Tensión en el ADC [mV]")
    plt.title("Señal EMG grabada por BLE")
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()