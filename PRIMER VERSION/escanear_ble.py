r"""Lista todos los dispositivos BLE que la compu ve durante 10 segundos.

Sirve para verificar que la ESP32-C3 ("MyoSignals") esta prendida y visible
antes de grabar.

PASOS PREVIOS (una sola vez):
    1. Abrir una terminal (PowerShell) en la carpeta APPBLE.
    2. Crear el entorno virtual (si todavia no existe la carpeta .venv):
           python -m venv .venv
    3. Activarlo:
           .venv\Scripts\Activate.ps1
       (si PowerShell no deja, correr antes:
           Set-ExecutionPolicy -Scope CurrentUser RemoteSigned)
    4. Instalar las dependencias:
           pip install -r "PRIMER VERSION\requirements.txt"

PARA CORRERLO:
    1. Prender el Bluetooth de la compu.
    2. Prender la ESP32-C3 (debe estar transmitiendo como "MyoSignals").
    3. Con el entorno virtual activado, entrar a la carpeta del script:
           cd "PRIMER VERSION"
    4. Ejecutar:
           python escanear_ble.py
    5. Esperar 10 s. Se imprime la lista de dispositivos ordenada por señal
       (RSSI); buscar "MyoSignals" en la lista.

No guarda ningun archivo.
"""
import asyncio

from bleak import BleakScanner


async def main():
    print("Escaneando 10 s...")
    encontrados = await BleakScanner.discover(timeout=10, return_adv=True)
    if not encontrados:
        print("No se vio ningun dispositivo. ¿Esta prendido el Bluetooth de la compu?")
        return
    filas = sorted(encontrados.values(), key=lambda x: x[1].rssi, reverse=True)
    for dev, adv in filas:
        nombre = adv.local_name or dev.name or "(sin nombre)"
        print(f"{adv.rssi:>5} dBm  {dev.address}  {nombre}")


asyncio.run(main())
