r"""Grafica una señal EMG guardada como CSV.

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
    1. Tener el CSV dentro de la carpeta "outputs" (lo genera grabar_emg.py).
    2. Con el entorno virtual activado, entrar a la carpeta del script:
           cd "PRIMER VERSION"
    3. Ejecutar indicando el nombre del CSV (solo el nombre, se busca en outputs):
           python graficar_csv.py prueba3.csv
       Sin argumentos grafica "pruea2.csv":
           python graficar_csv.py
       Tambien acepta una ruta completa a un CSV que exista en otro lado.
    4. Se abre una ventana con el grafico; cerrarla para terminar.

SALIDA:
    El PNG se guarda siempre en la carpeta "graficos" con el mismo nombre
    que el CSV (por ejemplo outputs/prueba3.csv -> graficos/prueba3.png).
"""

import csv
import os
import sys

import matplotlib.pyplot as plt

CARPETA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CARPETA_OUTPUTS = os.path.join(CARPETA_SCRIPT, "outputs")
CARPETA_GRAFICOS = os.path.join(CARPETA_SCRIPT, "graficos")


def main():
    nombre = sys.argv[1] if len(sys.argv) > 1 else "pruea2.csv"
    # si la ruta dada no existe, se busca el archivo dentro de outputs/
    path = nombre if os.path.isfile(nombre) else os.path.join(CARPETA_OUTPUTS, nombre)
    tiempos = []
    valores = []

    with open(path, newline="", encoding="utf-8-sig") as archivo:
        lector = csv.DictReader(archivo)
        columnas = lector.fieldnames or []
        if not {"t_s", "mV"}.issubset(columnas):
            raise ValueError(
                f"El CSV debe tener las columnas 't_s' y 'mV'; encontré: {columnas}"
            )

        for fila in lector:
            tiempos.append(float(fila["t_s"]))
            valores.append(float(fila["mV"]))

    if not tiempos:
        raise ValueError(f"El archivo no contiene muestras: {path}")

    plt.figure(figsize=(12, 4))
    plt.plot(tiempos, valores, linewidth=0.5)
    plt.xlabel("Tiempo [s]")
    plt.ylabel("Valor ADC")
    plt.title(f"Señal EMG: {os.path.basename(path)}")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    os.makedirs(CARPETA_GRAFICOS, exist_ok=True)
    base = os.path.splitext(os.path.basename(path))[0]
    imagen = os.path.join(CARPETA_GRAFICOS, base + ".png")
    plt.savefig(imagen, dpi=150)
    print(f"Gráfico guardado en {imagen}")
    plt.show()


if __name__ == "__main__":
    main()
