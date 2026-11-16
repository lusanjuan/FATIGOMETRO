"""Interfaz para registrar EMG por BLE o probar la pantalla con datos simulados."""

import argparse
import asyncio
import csv
import math
import os
import random
import re
import struct
import threading
import time
import unicodedata
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Optional

from bleak import BleakClient, BleakScanner
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

DEVICE_NAME = "MyoSignals"
EMG_UUID = "8d1f0002-6c3a-4b8e-9a2e-3f1b2c4d5e60"
FS = 2000
BLOCK = 100
SEGUNDOS_EN_PANTALLA = 5
MODOS = ("ESP32 por Bluetooth", "Demostración (sin ESP32)")
SEXOS = ("Femenino", "Masculino")

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
            "Demostración: señal simulada."
            if es_demo
            else "Preparando conexión con la ESP32..."
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
            prefijo = "Demo: " if self.es_demo else ""
            self.mensaje = (
                f"{prefijo}fatiga marcada en t = {numero_muestra / FS:.3f} s"
            )
            return numero_muestra / FS


def simular(captura: Captura, duracion: float, detener: threading.Event) -> None:
    generador = random.Random()
    numero_paquete = 0
    tiempo_inicio = time.monotonic()
    captura.actualizar_estado(
        "Demostración activa: señal simulada, no es una medición real.",
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
            f"Leyendo {duracion:g} s. Marca la fatiga cuando corresponda.",
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


def nombre_seguro(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto)
    ascii_texto = sin_acentos.encode("ascii", "ignore").decode("ascii")
    nombre = re.sub(r"[^A-Za-z0-9]+", "_", ascii_texto).strip("_").lower()
    return nombre or "participante"


def crear_rutas(
    usuario: str, sexo: str, es_demo: bool, fecha: Optional[datetime] = None
) -> tuple[str, str]:
    fecha = fecha or datetime.now()
    base = f"{nombre_seguro(usuario)}_{sexo.lower()}_{fecha:%Y%m%d_%H%M%S}"
    if es_demo:
        base = f"demo_{base}"

    candidato = base
    numero = 2
    while (
        os.path.exists(os.path.join(CARPETA_OUTPUTS, candidato + ".csv"))
        or os.path.exists(os.path.join(CARPETA_GRAFICOS, candidato + ".png"))
    ):
        candidato = f"{base}_{numero}"
        numero += 1

    return (
        os.path.join(CARPETA_OUTPUTS, candidato + ".csv"),
        os.path.join(CARPETA_GRAFICOS, candidato + ".png"),
    )


def guardar_csv(
    ruta: str,
    muestras: list[tuple[int, int]],
    marcas: set[int],
    usuario: str,
    sexo: str,
    modo: str,
) -> None:
    with open(ruta, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(
            ["usuario", "sexo", "modo", "muestra", "t_s", "mV", "fatiga"]
        )
        for numero_muestra, valor in muestras:
            escritor.writerow(
                [
                    usuario,
                    sexo,
                    modo,
                    numero_muestra,
                    f"{numero_muestra / FS:.4f}",
                    valor,
                    int(numero_muestra in marcas),
                ]
            )


class InterfazCaptura:
    def __init__(self, raiz: tk.Tk, duracion_inicial: float, demo_inicial: bool):
        self.raiz = raiz
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.captura: Optional[Captura] = None
        self.detener = threading.Event()
        self.future: Optional[Future] = None
        self.en_captura = False
        self.cerrar_despues = False
        self.usuario_actual = ""
        self.sexo_actual = ""
        self.modo_actual = "ble"

        self.raiz.title("Tomar muestras · Señal EMG")
        self.raiz.geometry("1080x760")
        self.raiz.minsize(860, 640)
        self.raiz.configure(bg="#F3F6FA")
        self.raiz.protocol("WM_DELETE_WINDOW", self.al_cerrar)

        self._configurar_estilos()
        self._construir_interfaz(duracion_inicial, demo_inicial)

    def _configurar_estilos(self) -> None:
        estilo = ttk.Style(self.raiz)
        estilo.theme_use("clam")
        estilo.configure("Fondo.TFrame", background="#F3F6FA")
        estilo.configure("Tarjeta.TFrame", background="#FFFFFF")
        estilo.configure(
            "Titulo.TLabel",
            background="#F3F6FA",
            foreground="#172B4D",
            font=("Segoe UI", 22, "bold"),
        )
        estilo.configure(
            "Subtitulo.TLabel",
            background="#F3F6FA",
            foreground="#64748B",
            font=("Segoe UI", 10),
        )
        estilo.configure(
            "TarjetaTitulo.TLabel",
            background="#FFFFFF",
            foreground="#172B4D",
            font=("Segoe UI", 12, "bold"),
        )
        estilo.configure(
            "Campo.TLabel",
            background="#FFFFFF",
            foreground="#475569",
            font=("Segoe UI", 9, "bold"),
        )
        estilo.configure(
            "Nota.TLabel",
            background="#FFFFFF",
            foreground="#64748B",
            font=("Segoe UI", 9),
        )
        estilo.configure(
            "Estado.TLabel",
            background="#FFFFFF",
            foreground="#334155",
            font=("Segoe UI", 10),
        )
        estilo.configure(
            "Primary.TButton",
            background="#2563EB",
            foreground="#FFFFFF",
            padding=(16, 10),
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
        )
        estilo.map(
            "Primary.TButton",
            background=[("disabled", "#94A3B8"), ("active", "#1D4ED8")],
        )
        estilo.configure(
            "Fatiga.TButton",
            background="#DC3F5C",
            foreground="#FFFFFF",
            padding=(16, 10),
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
        )
        estilo.map(
            "Fatiga.TButton",
            background=[("disabled", "#E2A3AD"), ("active", "#BE314B")],
        )
        estilo.configure(
            "Secondary.TButton",
            background="#E7EDF5",
            foreground="#334155",
            padding=(14, 10),
            font=("Segoe UI", 9, "bold"),
            borderwidth=0,
        )
        estilo.map(
            "Secondary.TButton",
            background=[("disabled", "#F1F5F9"), ("active", "#D7E0EC")],
        )
        estilo.configure(
            "TEntry",
            padding=8,
            fieldbackground="#FFFFFF",
            foreground="#172B4D",
            bordercolor="#CBD5E1",
        )
        estilo.configure(
            "TCombobox",
            padding=7,
            fieldbackground="#FFFFFF",
            foreground="#172B4D",
        )

    def _construir_interfaz(
        self, duracion_inicial: float, demo_inicial: bool
    ) -> None:
        contenedor = ttk.Frame(self.raiz, style="Fondo.TFrame", padding=(24, 20))
        contenedor.pack(fill="both", expand=True)
        contenedor.columnconfigure(0, weight=1)
        contenedor.rowconfigure(2, weight=1)

        cabecera = ttk.Frame(contenedor, style="Fondo.TFrame")
        cabecera.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        ttk.Label(
            cabecera,
            text="Registro de señal EMG",
            style="Titulo.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            cabecera,
            text="Completa los datos de la muestra y marca la fatiga durante la lectura.",
            style="Subtitulo.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        tarjeta_datos = ttk.Frame(
            contenedor, style="Tarjeta.TFrame", padding=(18, 15)
        )
        tarjeta_datos.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        for columna, peso in enumerate((3, 2, 1, 2)):
            tarjeta_datos.columnconfigure(columna, weight=peso)

        ttk.Label(
            tarjeta_datos,
            text="Datos de la muestra",
            style="TarjetaTitulo.TLabel",
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

        ttk.Label(
            tarjeta_datos, text="Nombre o apodo", style="Campo.TLabel"
        ).grid(row=1, column=0, sticky="w", padx=(0, 12))
        ttk.Label(tarjeta_datos, text="Sexo", style="Campo.TLabel").grid(
            row=1, column=1, sticky="w", padx=(0, 12)
        )
        ttk.Label(
            tarjeta_datos, text="Duración (s)", style="Campo.TLabel"
        ).grid(row=1, column=2, sticky="w", padx=(0, 12))
        ttk.Label(
            tarjeta_datos, text="Fuente de señal", style="Campo.TLabel"
        ).grid(row=1, column=3, sticky="w")

        self.usuario_var = tk.StringVar()
        self.sexo_var = tk.StringVar()
        self.duracion_var = tk.StringVar(value=f"{duracion_inicial:g}")
        self.modo_var = tk.StringVar(
            value=MODOS[1] if demo_inicial else MODOS[0]
        )
        self.usuario_entry = ttk.Entry(
            tarjeta_datos, textvariable=self.usuario_var
        )
        self.usuario_entry.grid(
            row=2, column=0, sticky="ew", padx=(0, 12), pady=(5, 0)
        )
        self.sexo_combo = ttk.Combobox(
            tarjeta_datos,
            textvariable=self.sexo_var,
            values=SEXOS,
            state="readonly",
        )
        self.sexo_combo.grid(
            row=2, column=1, sticky="ew", padx=(0, 12), pady=(5, 0)
        )
        self.duracion_entry = ttk.Entry(
            tarjeta_datos, textvariable=self.duracion_var
        )
        self.duracion_entry.grid(
            row=2, column=2, sticky="ew", padx=(0, 12), pady=(5, 0)
        )
        self.modo_combo = ttk.Combobox(
            tarjeta_datos,
            textvariable=self.modo_var,
            values=MODOS,
            state="readonly",
        )
        self.modo_combo.grid(row=2, column=3, sticky="ew", pady=(5, 0))
        ttk.Label(
            tarjeta_datos,
            text="El nombre se limpia para el archivo; en el CSV se conserva como lo escribiste.",
            style="Nota.TLabel",
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(9, 12))

        controles = ttk.Frame(tarjeta_datos, style="Tarjeta.TFrame")
        controles.grid(row=4, column=0, columnspan=4, sticky="ew")
        self.iniciar_boton = ttk.Button(
            controles,
            text="Iniciar captura",
            style="Primary.TButton",
            command=self.iniciar_captura,
        )
        self.iniciar_boton.pack(side="left")
        self.marcar_boton = ttk.Button(
            controles,
            text="Marcar fatiga",
            style="Fatiga.TButton",
            command=self.marcar_fatiga,
            state="disabled",
        )
        self.marcar_boton.pack(side="left", padx=(10, 0))
        self.detener_boton = ttk.Button(
            controles,
            text="Detener y guardar",
            style="Secondary.TButton",
            command=self.detener_captura,
            state="disabled",
        )
        self.detener_boton.pack(side="left", padx=(10, 0))

        tarjeta_grafico = ttk.Frame(
            contenedor, style="Tarjeta.TFrame", padding=(12, 12)
        )
        tarjeta_grafico.grid(row=2, column=0, sticky="nsew", pady=(0, 14))
        tarjeta_grafico.columnconfigure(0, weight=1)
        tarjeta_grafico.rowconfigure(0, weight=1)

        self.figura = Figure(figsize=(9, 4), dpi=100, facecolor="#FFFFFF")
        self.eje = self.figura.add_subplot(111)
        self.eje.set_facecolor("#FBFCFE")
        self.linea, = self.eje.plot([], [], color="#2563EB", linewidth=0.8)
        self.puntos_fatiga, = self.eje.plot(
            [], [], "x", color="#DC3F5C", markersize=9, markeredgewidth=2
        )
        self.eje.set_xlim(0, SEGUNDOS_EN_PANTALLA)
        self.eje.set_xlabel("Tiempo [s]")
        self.eje.set_ylabel("Señal ADC [mV]")
        self.eje.set_title("La señal aparecerá aquí al iniciar la captura")
        self.eje.grid(True, color="#E2E8F0", alpha=0.9)
        self.figura.tight_layout()
        self.canvas = FigureCanvasTkAgg(self.figura, master=tarjeta_grafico)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self.canvas.draw()

        barra_estado = ttk.Frame(
            contenedor, style="Tarjeta.TFrame", padding=(14, 10)
        )
        barra_estado.grid(row=3, column=0, sticky="ew")
        barra_estado.columnconfigure(0, weight=1)
        self.estado_var = tk.StringVar(
            value="Listo. Completa los datos para comenzar."
        )
        ttk.Label(
            barra_estado, textvariable=self.estado_var, style="Estado.TLabel"
        ).grid(row=0, column=0, sticky="w")

    def iniciar_captura(self) -> None:
        usuario = self.usuario_var.get().strip()
        sexo = self.sexo_var.get()
        try:
            duracion = float(self.duracion_var.get().replace(",", "."))
        except ValueError:
            messagebox.showwarning(
                "Duración inválida",
                "Escribe la duración en segundos, por ejemplo 30.",
                parent=self.raiz,
            )
            return

        if not usuario:
            messagebox.showwarning(
                "Falta el nombre o apodo",
                "Completa el dato que identifica a la persona.",
                parent=self.raiz,
            )
            self.usuario_entry.focus_set()
            return
        if sexo not in SEXOS:
            messagebox.showwarning(
                "Falta seleccionar el sexo",
                "Elige Femenino o Masculino para esta muestra.",
                parent=self.raiz,
            )
            self.sexo_combo.focus_set()
            return
        if not math.isfinite(duracion) or duracion <= 0:
            messagebox.showwarning(
                "Duración inválida",
                "La duración debe ser un número mayor que cero.",
                parent=self.raiz,
            )
            self.duracion_entry.focus_set()
            return

        self.usuario_actual = usuario
        self.sexo_actual = sexo
        self.modo_actual = "demo" if self.modo_var.get() == MODOS[1] else "ble"
        es_demo = self.modo_actual == "demo"
        self.captura = Captura(es_demo=es_demo)
        self.detener = threading.Event()
        self.en_captura = True
        self._configurar_controles(durante_captura=True)
        self._limpiar_grafico()
        if es_demo:
            self.eje.set_title("Demostración en vivo (señal simulada)")
            self.estado_var.set("Demostración iniciada; no se conecta a la ESP32.")
            self.future = self.executor.submit(
                simular, self.captura, duracion, self.detener
            )
        else:
            self.eje.set_title(f"Buscando {DEVICE_NAME}...")
            self.estado_var.set(
                f"Buscando {DEVICE_NAME}. Enciende la ESP32 y el Bluetooth."
            )
            self.future = self.executor.submit(
                asyncio.run,
                capturar(self.captura, duracion, self.detener),
            )
        self.canvas.draw_idle()
        self.raiz.after(100, self.actualizar_vista)

    def actualizar_vista(self) -> None:
        if not self.en_captura or self.captura is None or self.future is None:
            return

        muestras, marcas, mensaje, iniciada, _ = self.captura.instantanea(
            FS * SEGUNDOS_EN_PANTALLA
        )
        if muestras:
            tiempos = [numero / FS for numero, _ in muestras]
            valores = [valor for _, valor in muestras]
            self.linea.set_data(tiempos, valores)
            fin = tiempos[-1]
            limite = max(fin, SEGUNDOS_EN_PANTALLA)
            self.eje.set_xlim(max(0, limite - SEGUNDOS_EN_PANTALLA), limite)
            self.eje.relim()
            self.eje.autoscale_view(scalex=False, scaley=True)
            valores_por_muestra = dict(muestras)
            marcas_visibles = [
                (numero / FS, valores_por_muestra[numero])
                for numero in marcas
                if numero in valores_por_muestra
            ]
            self.puntos_fatiga.set_data(
                [tiempo for tiempo, _ in marcas_visibles],
                [valor for _, valor in marcas_visibles],
            )
            self.canvas.draw_idle()

        if mensaje:
            self.estado_var.set(mensaje)
        self.marcar_boton.configure(
            state="normal" if iniciada else "disabled"
        )

        if self.future.done():
            self.finalizar_captura()
        else:
            self.raiz.after(100, self.actualizar_vista)

    def marcar_fatiga(self) -> None:
        if self.captura is None:
            return
        tiempo = self.captura.marcar_ultima_muestra()
        if tiempo is None:
            self.estado_var.set("Espera a que empiece la lectura para marcar.")
        else:
            self.estado_var.set(f"Fatiga marcada en t = {tiempo:.3f} s")

    def detener_captura(self) -> None:
        if self.en_captura:
            self.detener.set()
            if self.captura is not None:
                self.captura.actualizar_estado(
                    "Deteniendo la lectura y guardando los datos..."
                )
            self.estado_var.set("Deteniendo la lectura y guardando los datos...")
            self.detener_boton.configure(state="disabled")

    def finalizar_captura(self) -> None:
        if not self.en_captura or self.captura is None or self.future is None:
            return

        error = self.future.exception()
        if error is not None:
            self.estado_var.set(f"Error: {error}")
            messagebox.showerror(
                "No se pudo completar la captura",
                str(error),
                parent=self.raiz,
            )
        else:
            muestras, marcas, _, _, _ = self.captura.instantanea()
            if not muestras:
                self.estado_var.set(
                    "No llegaron muestras. Revisa la conexión con la ESP32."
                )
                messagebox.showwarning(
                    "Sin muestras",
                    "No llegaron datos; no se generaron archivos.",
                    parent=self.raiz,
                )
            else:
                self.guardar_resultados(muestras, marcas)

        self.en_captura = False
        self._configurar_controles(durante_captura=False)
        if self.cerrar_despues:
            self.executor.shutdown(wait=False)
            self.raiz.destroy()

    def guardar_resultados(
        self, muestras: list[tuple[int, int]], marcas: set[int]
    ) -> None:
        es_demo = self.modo_actual == "demo"
        ruta_csv, ruta_png = crear_rutas(
            self.usuario_actual, self.sexo_actual, es_demo
        )
        try:
            os.makedirs(CARPETA_OUTPUTS, exist_ok=True)
            os.makedirs(CARPETA_GRAFICOS, exist_ok=True)
            guardar_csv(
                ruta_csv,
                muestras,
                marcas,
                self.usuario_actual,
                self.sexo_actual,
                self.modo_actual,
            )
            import graficar_csv

            graficar_csv.graficar_datos(
                [numero / FS for numero, _ in muestras],
                [valor for _, valor in muestras],
                [numero / FS for numero in marcas],
                ruta_png,
                titulo=f"{self.usuario_actual} · {self.sexo_actual}",
                mostrar=False,
            )
        except (OSError, ValueError) as error:
            self.estado_var.set(f"Error al guardar los archivos: {error}")
            messagebox.showerror(
                "Error al guardar",
                str(error),
                parent=self.raiz,
            )
            return

        etiqueta = "Demostración guardada" if es_demo else "Captura guardada"
        self.estado_var.set(
            f"{etiqueta}: {os.path.basename(ruta_csv)}  ·  "
            f"{len(marcas)} marca(s) de fatiga"
        )

    def _configurar_controles(self, durante_captura: bool) -> None:
        estado_campo = "disabled" if durante_captura else "normal"
        self.usuario_entry.configure(state=estado_campo)
        self.duracion_entry.configure(state=estado_campo)
        self.sexo_combo.configure(
            state="disabled" if durante_captura else "readonly"
        )
        self.modo_combo.configure(
            state="disabled" if durante_captura else "readonly"
        )
        self.iniciar_boton.configure(
            state="disabled" if durante_captura else "normal"
        )
        self.detener_boton.configure(
            state="normal" if durante_captura else "disabled"
        )
        if not durante_captura:
            self.marcar_boton.configure(state="disabled")

    def _limpiar_grafico(self) -> None:
        self.linea.set_data([], [])
        self.puntos_fatiga.set_data([], [])
        self.eje.set_xlim(0, SEGUNDOS_EN_PANTALLA)

    def al_cerrar(self) -> None:
        if self.en_captura:
            self.cerrar_despues = True
            self.detener.set()
            if self.captura is not None:
                self.captura.actualizar_estado(
                    "Deteniendo la lectura antes de cerrar..."
                )
            self.estado_var.set("Deteniendo la lectura antes de cerrar...")
            self.detener_boton.configure(state="disabled")
            return
        self.executor.shutdown(wait=False)
        self.raiz.destroy()


def crear_argumentos() -> argparse.Namespace:
    analizador = argparse.ArgumentParser(
        description="Abre la interfaz para registrar muestras EMG."
    )
    analizador.add_argument(
        "duracion",
        nargs="?",
        type=float,
        default=30,
        help="duración inicial en segundos (por defecto: 30)",
    )
    analizador.add_argument(
        "--demo",
        action="store_true",
        help="selecciona la señal simulada en la interfaz",
    )
    argumentos = analizador.parse_args()
    if not math.isfinite(argumentos.duracion) or argumentos.duracion <= 0:
        analizador.error("la duración debe ser un número positivo")
    return argumentos


def main() -> None:
    argumentos = crear_argumentos()
    raiz = tk.Tk()
    InterfazCaptura(raiz, argumentos.duracion, argumentos.demo)
    raiz.mainloop()


if __name__ == "__main__":
    main()
