"""Grafica una señal EMG guardada como CSV.

Uso:
    python graficar_csv.py
    python graficar_csv.py otro_archivo.csv
"""

import csv
import os
import sys

import matplotlib.pyplot as plt


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "pruea2.csv"
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

    imagen = os.path.splitext(path)[0] + ".png"
    plt.savefig(imagen, dpi=150)
    print(f"Gráfico guardado en {imagen}")
    plt.show()


if __name__ == "__main__":
    main()
