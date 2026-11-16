"""Grafica un CSV de EMG y resalta las muestras marcadas como fatiga."""

import argparse
import csv
import os

import matplotlib.pyplot as plt

CARPETA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CARPETA_OUTPUTS = os.path.join(CARPETA_SCRIPT, "outputs")
CARPETA_GRAFICOS = os.path.join(CARPETA_SCRIPT, "graficos")


def leer_csv(ruta: str) -> tuple[list[float], list[float], list[float]]:
    tiempos = []
    valores = []
    marcas = []
    with open(ruta, newline="", encoding="utf-8-sig") as archivo:
        lector = csv.DictReader(archivo)
        columnas = lector.fieldnames or []
        if not {"t_s", "mV"}.issubset(columnas):
            raise ValueError(
                f"El CSV debe tener las columnas 't_s' y 'mV'; encontré: {columnas}"
            )

        for fila in lector:
            tiempo = float(fila["t_s"])
            tiempos.append(tiempo)
            valores.append(float(fila["mV"]))
            if fila.get("fatiga", "0") == "1":
                marcas.append(tiempo)

    if not tiempos:
        raise ValueError(f"El archivo no contiene muestras: {ruta}")
    return tiempos, valores, marcas


def graficar_datos(
    tiempos: list[float],
    valores: list[float],
    marcas: list[float],
    ruta_imagen: str,
    *,
    titulo: str,
    mostrar: bool = True,
) -> None:
    figura, eje = plt.subplots(figsize=(12, 4))
    eje.plot(tiempos, valores, linewidth=0.5)
    for indice, tiempo in enumerate(marcas):
        eje.axvline(
            tiempo,
            color="red",
            linestyle="--",
            linewidth=1,
            label="Fatiga" if indice == 0 else None,
        )
    eje.set_xlabel("Tiempo [s]")
    eje.set_ylabel("Valor ADC [mV]")
    eje.set_title(titulo)
    eje.grid(True, alpha=0.3)
    if marcas:
        eje.legend()
    figura.tight_layout()
    figura.savefig(ruta_imagen, dpi=150)
    if mostrar:
        plt.show(block=True)
    plt.close(figura)


def main() -> None:
    analizador = argparse.ArgumentParser(
        description="Grafica un CSV de EMG y resalta los momentos de fatiga."
    )
    analizador.add_argument("csv", help="ruta o nombre del CSV a graficar")
    nombre = analizador.parse_args().csv
    ruta = nombre if os.path.isfile(nombre) else os.path.join(CARPETA_OUTPUTS, nombre)
    tiempos, valores, marcas = leer_csv(ruta)
    os.makedirs(CARPETA_GRAFICOS, exist_ok=True)
    base = os.path.splitext(os.path.basename(ruta))[0]
    ruta_imagen = os.path.join(CARPETA_GRAFICOS, base + ".png")
    graficar_datos(
        tiempos,
        valores,
        marcas,
        ruta_imagen,
        titulo=f"Señal EMG: {base}",
    )
    print(f"Gráfico guardado en {ruta_imagen}")


if __name__ == "__main__":
    main()
