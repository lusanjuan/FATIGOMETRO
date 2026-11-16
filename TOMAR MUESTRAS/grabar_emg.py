"""Graba EMG por BLE, muestra la señal en vivo y permite marcar fatiga."""

import argparse
import asyncio
import csv
import math
import os
import random
import struct
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Optional

import matplotlib.pyplot as plt
from matplotlib.widgets import Button
from bleak import BleakClient, BleakScanner

DEVICE_NAME = "MyoSignals"
EMG_UUID = "8d1f0002-6c3a-4b8e-9a2e-3f1b2c4d5e60"
FS = 2000
BLOCK = 100
SEGUNDOS_EN_PANTALLA = 5

CARPETA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CARPETA_OUTPUTS = os.path.join(CARPETA_SCRIPT, "outputs")
CARPETA_GRAFICOS = os.path.join(CARPETA_SCRIPT, "graficos")


class Captura:
    def __init__(self, es_demo: bool = False) -> None:
        self.lock = threading.Lock()
        self.es_demo = es_demo
        self.muestras: list[tuple[int, int]] = []
        self.marcas: set[int] = set()
        self.numero_muestra = 0
        self.ultimo_paquete: Optional[int] = None
        self.paquetes_perdidos = 0
        self.paquetes_recibidos = 0
        self.iniciada = False
        self.finalizada = False
        self.mensaje = (
            "DEMOSTRACIÓN: generando señal simulada..."
            if es_demo
            else "Buscando la ESP32..."
        )

    def recibir(self, numero_paquete: int, valores: tuple[int, ...]) -> None:
        with self.lock:
            if self.ultimo_paquete is not None:
                salto = (numero_paquete - self.ultimo_paquete - 1) & 0xFFFF
                if salto:
                    self.paquetes_perdidos += salto
                    self.numero_muestra += salto * BLOCK

            self.ultimo_paquete = numero_paquete
            self.paquetes_recibidos += 1
            for valor in valores:
                self.muestras.append((self.numero_muestra, valor))
                self.numero_muestra += 1

    def instantanea(
        self, maximo_muestras: Optional[int] = None
    ) -> tuple[list[tuple[int, int]], set[int], str, bool, bool]:
        with self.lock:
            muestras = (
                self.muestras[-maximo_muestras:]
                if maximo_muestras is not None
                else self.muestras.copy()
            )
            marcas = self.marcas.copy()
            if maximo_muestras is not None and muestras:
                primer_numero = muestras[0][0]
                marcas = {numero for numero in marcas if numero >= primer_numero}
            return (
                muestras,
                marcas,
                self.mensaje,
                self.iniciada,
                self.finalizada,
            )

    def actualizar_estado(
        self,
        mensaje: Optional[str] = None,
        *,
        iniciada: Optional[bool] = None,
        finalizada: Optional[bool] = None,
    ) -> None:
        with self.lock:
            if mensaje is not None:
                self.mensaje = mensaje
            if iniciada is not None:
                self.iniciada = iniciada
            if finalizada is not None:
                self.finalizada = finalizada

    def marcar_ultima_muestra(self) -> Optional[float]:
        with self.lock:
            if not self.iniciada or self.finalizada or not self.muestras:
                return None
            numero_muestra = self.muestras[-1][0]
            self.marcas.add(numero_muestra)
            prefijo = "DEMO: " if self.es_demo else ""
            self.mensaje = (
                f"{prefijo}Fatiga marcada en t = {numero_muestra / FS:.3f} s"
            )
            return numero_muestra / FS


def simular(captura: Captura, duracion: float, detener: threading.Event) -> None:
    generador = random.Random()
    numero_paquete = 0
    tiempo_inicio = time.monotonic()
    captura.actualizar_estado(
        "DEMOSTRACIÓN: señal simulada. No se conecta a la ESP32.",
        iniciada=True,
    )
    try:
        while time.monotonic() - tiempo_inicio < duracion and not detener.is_set():
            inicio_muestra = numero_paquete * BLOCK
            valores = []
            for desplazamiento in range(BLOCK):
                tiempo = (inicio_muestra + desplazamiento) / FS
                envolvente = 20 + 15 * (1 + math.sin(2 * math.pi * 0.3 * tiempo))
                oscilacion = (
                    0.65 * math.sin(2 * math.pi * 73 * tiempo)
                    + 0.35 * math.sin(2 * math.pi * 121 * tiempo)
                )
                ruido = generador.gauss(0, 7 + envolvente * 0.8)
                valor = round(660 + 2 * envolvente * oscilacion + ruido)
                valores.append(max(0, min(1300, valor)))

            captura.recibir(numero_paquete, tuple(valores))
            numero_paquete = (numero_paquete + 1) & 0xFFFF
            time.sleep(0.05)
    finally:
        captura.actualizar_estado(finalizada=True)


async def capturar(
    captura: Captura, duracion: float, detener: threading.Event
) -> None:
    dispositivo = await BleakScanner.find_device_by_name(
        DEVICE_NAME, timeout=15
    )
    if dispositivo is None:
        raise RuntimeError(
            f"No se encontró '{DEVICE_NAME}'. Revisa Bluetooth y la ESP32."
        )

    def al_recibir_datos(_, datos: bytearray) -> None:
        if len(datos) < 4 or (len(datos) - 2) % 2:
            raise ValueError("La ESP32 envió un paquete BLE con formato inválido.")
        numero_paquete = struct.unpack_from("<H", datos, 0)[0]
        cantidad = (len(datos) - 2) // 2
        valores = struct.unpack_from(f"<{cantidad}H", datos, 2)
        captura.recibir(numero_paquete, valores)

    async with BleakClient(dispositivo) as cliente:
        captura.actualizar_estado("Conectada. Iniciando lectura...")
        await cliente.start_notify(EMG_UUID, al_recibir_datos)
        captura.actualizar_estado(
            f"Leyendo señal. Duración: {duracion:g} s. Marca la fatiga en el botón.",
            iniciada=True,
        )
        tiempo_inicio = asyncio.get_running_loop().time()
        try:
            while (
                asyncio.get_running_loop().time() - tiempo_inicio < duracion
                and not detener.is_set()
            ):
                await asyncio.sleep(0.05)
        finally:
            await cliente.stop_notify(EMG_UUID)
            captura.actualizar_estado(finalizada=True)


def guardar_csv(
    ruta: str, muestras: list[tuple[int, int]], marcas: set[int]
) -> None:
    with open(ruta, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["muestra", "t_s", "mV", "fatiga"])
        for numero_muestra, valor in muestras:
            escritor.writerow(
                [
                    numero_muestra,
                    f"{numero_muestra / FS:.4f}",
                    valor,
                    int(numero_muestra in marcas),
                ]
            )


def dibujar_en_vivo(captura: Captura, future: Future, detener: threading.Event):
    figura, eje = plt.subplots(figsize=(12, 5))
    figura.subplots_adjust(bottom=0.2)
    linea, = eje.plot([], [], linewidth=0.6)
    puntos_fatiga, = eje.plot(
        [], [], "rx", markersize=8, markeredgewidth=2, zorder=3
    )
    texto_estado = figura.text(0.12, 0.08, "", ha="left")
    eje.set_xlabel("Tiempo [s]")
    eje.set_ylabel("Valor ADC [mV]")
    eje.set_title(
        "DEMOSTRACIÓN: señal simulada"
        if captura.es_demo
        else "Señal EMG en vivo"
    )
    eje.grid(True, alpha=0.3)

    area_boton = figura.add_axes([0.72, 0.045, 0.2, 0.08])
    boton = Button(area_boton, "Marcar fatiga")

    def al_hacer_clic(_evento) -> None:
        if captura.marcar_ultima_muestra() is None:
            captura.actualizar_estado(
                "Espera a que comience la lectura para marcar fatiga."
            )

    boton.on_clicked(al_hacer_clic)
    error_mostrado = [False]

    def actualizar(_marco):
        muestras, marcas, mensaje, _, finalizada = captura.instantanea(
            FS * SEGUNDOS_EN_PANTALLA
        )
        if muestras:
            visibles = muestras[-FS * SEGUNDOS_EN_PANTALLA :]
            tiempos = [numero / FS for numero, _ in visibles]
            valores = [valor for _, valor in visibles]
            linea.set_data(tiempos, valores)
            fin = tiempos[-1]
            inicio = max(0, fin - SEGUNDOS_EN_PANTALLA)
            eje.set_xlim(inicio, max(fin, SEGUNDOS_EN_PANTALLA))
            eje.relim()
            eje.autoscale_view(scalex=False, scaley=True)
            visibles_por_numero = {numero: valor for numero, valor in visibles}
            marcadores_visibles = [
                (numero / FS, visibles_por_numero[numero])
                for numero in marcas
                if numero in visibles_por_numero
            ]
            puntos_fatiga.set_data(
                [tiempo for tiempo, _ in marcadores_visibles],
                [valor for _, valor in marcadores_visibles],
            )

        texto_estado.set_text(mensaje)
        if future.done() and not error_mostrado[0]:
            error = future.exception()
            if error is not None:
                captura.actualizar_estado(
                    f"Error durante la captura: {type(error).__name__}: {error}",
                    finalizada=True,
                )
                error_mostrado[0] = True
            elif finalizada:
                texto_estado.set_text(
                    f"Lectura terminada. {mensaje} Cierra la ventana para guardar."
                )
        return linea, puntos_fatiga, texto_estado

    def al_cerrar(_evento) -> None:
        detener.set()

    figura.canvas.mpl_connect("close_event", al_cerrar)
    temporizador = figura.canvas.new_timer(interval=100)
    temporizador.add_callback(actualizar, 0)
    temporizador.start()
    plt.show(block=True)


def crear_argumentos() -> argparse.Namespace:
    analizador = argparse.ArgumentParser(
        description="Registra EMG y permite marcar momentos de fatiga."
    )
    analizador.add_argument(
        "duracion",
        nargs="?",
        type=float,
        default=30,
        help="duración de la captura en segundos (por defecto: 30)",
    )
    analizador.add_argument(
        "--demo",
        action="store_true",
        help="muestra una señal simulada sin conectarse a la ESP32",
    )
    argumentos = analizador.parse_args()
    if not math.isfinite(argumentos.duracion) or argumentos.duracion <= 0:
        analizador.error("la duración debe ser un número positivo")
    return argumentos


def main() -> None:
    argumentos = crear_argumentos()
    os.makedirs(CARPETA_OUTPUTS, exist_ok=True)
    os.makedirs(CARPETA_GRAFICOS, exist_ok=True)

    prefijo = "demo_" if argumentos.demo else "muestra_"
    nombre = datetime.now().strftime(prefijo + "%Y%m%d_%H%M%S")
    ruta_csv = os.path.join(CARPETA_OUTPUTS, nombre + ".csv")
    ruta_png = os.path.join(CARPETA_GRAFICOS, nombre + ".png")

    captura = Captura(es_demo=argumentos.demo)
    detener = threading.Event()
    executor = ThreadPoolExecutor(max_workers=1)
    if argumentos.demo:
        future = executor.submit(simular, captura, argumentos.duracion, detener)
    else:
        future = executor.submit(
            asyncio.run, capturar(captura, argumentos.duracion, detener)
        )

    try:
        dibujar_en_vivo(captura, future, detener)
    finally:
        detener.set()
        executor.shutdown(wait=True)

    error = future.exception()
    if error is not None:
        raise error

    muestras, marcas, _, _, _ = captura.instantanea()
    if not muestras:
        raise RuntimeError("No se recibieron muestras; no se generaron archivos.")

    guardar_csv(ruta_csv, muestras, marcas)
    import graficar_csv

    graficar_csv.graficar_datos(
        [numero / FS for numero, _ in muestras],
        [valor for _, valor in muestras],
        [numero / FS for numero in marcas],
        ruta_png,
        titulo=f"Señal EMG: {nombre}",
    )
    print(
        f"Captura guardada: {ruta_csv}\n"
        f"Gráfico guardado: {ruta_png}\n"
        f"Paquetes recibidos: {captura.paquetes_recibidos}; "
        f"perdidos: {captura.paquetes_perdidos}; marcas: {len(marcas)}"
    )


if __name__ == "__main__":
    main()
