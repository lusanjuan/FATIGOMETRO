# Tomar muestras de EMG y marcar fatiga

Esta carpeta es una versión independiente para registrar la señal de la ESP32
por Bluetooth, verla mientras se recibe y marcar cuándo aparece la fatiga.
No modifica los archivos de `PRIMER VERSION`.

## Preparación

1. Usar la ESP32 con el firmware `emg_ble.ino` que ya funciona en
   `PRIMER VERSION`. La placa debe anunciarse como `MyoSignals`.
2. Desde la carpeta `APPBLE`, crear y activar un entorno virtual si todavía no
   existe:

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. Instalar las dependencias:

   ```powershell
   pip install -r "TOMAR MUESTRAS\requirements.txt"
   ```

## Registrar

Desde `APPBLE`, con la ESP32 encendida y Bluetooth habilitado:

```powershell
python "TOMAR MUESTRAS\grabar_emg.py" 60
```

Para ver la ventana y probar **Marcar fatiga** sin una ESP32, ejecutar:

```powershell
python "TOMAR MUESTRAS\grabar_emg.py" 30 --demo
```

La señal es simulada y los archivos resultantes llevan el prefijo `demo_`;
no representan una medición real.

El número indica la duración en segundos; si se omite, se graban 30 segundos.
Se abre un gráfico que se actualiza mientras llegan las muestras. Cuando la
persona sienta fatiga, debe hacer clic en **Marcar fatiga**. Se pueden marcar
varios momentos. Cerrar la ventana detiene una grabación que siga en curso.

Al cerrar la ventana, se guardan:

- Un CSV en `TOMAR MUESTRAS\outputs`, con `muestra`, `t_s`, `mV` y `fatiga`.
  La columna `fatiga` vale `1` en las muestras marcadas y `0` en las demás.
- Un PNG en `TOMAR MUESTRAS\graficos`, con una línea roja por cada marca.

El gráfico en vivo muestra los últimos cinco segundos para que la señal se
pueda observar con detalle. El PNG final muestra el registro completo.

## Ver un CSV guardado

```powershell
python "TOMAR MUESTRAS\graficar_csv.py" "TOMAR MUESTRAS\outputs\muestra.csv"
```

El botón asocia la marca con la última muestra recibida y disponible en el
gráfico. La ESP32 transmite bloques de 100 muestras (50 ms a 2000 Hz), por lo
que ese es el límite práctico de sincronización de la marca con la señal; el
firmware actual no envía la hora individual de cada muestra.
