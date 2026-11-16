# Tomar muestras de EMG y marcar fatiga

Esta carpeta contiene una interfaz para registrar la señal de la ESP32 por
Bluetooth, verla mientras se recibe y marcar cuándo aparece la fatiga. No
modifica los archivos de `PRIMER VERSION`.

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

## Abrir la interfaz

Desde `APPBLE`, con el entorno virtual activado, ejecutar:

```powershell
python "TOMAR MUESTRAS\grabar_emg.py"
```

En la ventana:

1. Escribir el nombre o apodo de la persona.
2. Elegir **Femenino** o **Masculino**.
3. Indicar la duración en segundos y la fuente de señal.
4. Hacer clic en **Iniciar captura**.
5. Durante la lectura, hacer clic en **Marcar fatiga** cada vez que corresponda.
   **Detener y guardar** termina la lectura antes del tiempo indicado.

Al terminar, se guardan automáticamente:

- Un CSV en `TOMAR MUESTRAS\outputs`.
- Un PNG en `TOMAR MUESTRAS\graficos`, con una línea roja por cada marca.

El nombre de archivo contiene el nombre o apodo, el sexo y la fecha, por
ejemplo `ana_perez_femenino_20261116_164500.csv`. Los nombres se limpian para
formar un nombre de archivo válido; el CSV conserva el nombre ingresado. Para
la demostración se antepone `demo_`.

El CSV incluye las columnas `usuario`, `sexo`, `modo`, `muestra`, `t_s`, `mV`
y `fatiga`. Así se pueden filtrar participantes y sexo directamente al
analizar los datos. `fatiga` vale `1` en las muestras marcadas y `0` en las
demás. Los datos se pueden revisar con una hoja de cálculo o con Python.

El gráfico en vivo muestra los últimos cinco segundos. Después de guardar, se
puede cambiar el participante y empezar otra captura sin cerrar la interfaz.

## Probar sin ESP32

```powershell
python "TOMAR MUESTRAS\grabar_emg.py" --demo
```

La interfaz abre con **Demostración (sin ESP32)** seleccionada. La señal es
simulada y no representa una medición real. También se puede ingresar una
duración inicial, por ejemplo `python "TOMAR MUESTRAS\grabar_emg.py" 60`.

## Graficar un CSV guardado

```powershell
python "TOMAR MUESTRAS\graficar_csv.py" "TOMAR MUESTRAS\outputs\ana_perez_femenino_20261116_164500.csv"
```

La marca se asocia a la última muestra recibida. La ESP32 transmite bloques
de 100 muestras (50 ms a 2000 Hz), por lo que ese es el límite práctico de
sincronización con el firmware actual.
