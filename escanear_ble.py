"""Lista todos los dispositivos BLE que la compu ve durante 10 segundos.

Uso:
    python escanear_ble.py
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
