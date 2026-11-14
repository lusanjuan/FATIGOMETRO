// MyoSignals - envio de la señal cruda de EMG por BLE (ESP32-C3 SuperMini)
// Muestrea GPIO0 a 2000 Hz y manda bloques de 100 muestras por notificacion BLE.
// Paquete: [seq uint16][100 x uint16 mV], little-endian = 202 bytes, 20 paquetes/s.
// Requiere el core ESP32 de Arduino >= 3.0 (incluye la libreria BLE).

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLE2902.h>
#include "esp_timer.h"

#define EMG_PIN   0      // EMG_OUTPUT -> GPIO0 (ADC1_CH0)
#define FS        2000   // frecuencia de muestreo [Hz]
#define BLOCK     100    // muestras por paquete (50 ms)
#define NBUF      8      // bloques en el buffer circular (400 ms de margen)
#define LED_PIN   3      // LED D1: prendido = conectado por BLE

#define SERVICE_UUID "8d1f0001-6c3a-4b8e-9a2e-3f1b2c4d5e60"
#define EMG_UUID     "8d1f0002-6c3a-4b8e-9a2e-3f1b2c4d5e60"

static uint16_t buf[NBUF][BLOCK];
static volatile uint16_t wPos = 0;
static volatile uint32_t blocksWritten = 0;   // bloques completos escritos
static uint32_t blocksSent = 0;               // bloques ya procesados

BLECharacteristic *emgChar = nullptr;
volatile bool connected = false;

// Se ejecuta cada 500 us (2000 Hz) en la tarea de esp_timer
static void sampleCb(void *) {
  uint32_t b = blocksWritten % NBUF;
  buf[b][wPos] = analogReadMilliVolts(EMG_PIN);
  if (++wPos >= BLOCK) {
    wPos = 0;
    blocksWritten++;
  }
}

class ServerCB : public BLEServerCallbacks {
  void onConnect(BLEServer *s) override { connected = true; }
  void onDisconnect(BLEServer *s) override {
    connected = false;               // el loop vuelve a anunciar
  }
};

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // ADC: 12 bits. Con atenuacion de 6 dB el rango del C3 es ~0-1300 mV,
  // adecuado para una señal centrada en ~0,66 V.
  analogReadResolution(12);
  analogSetPinAttenuation(EMG_PIN, ADC_6db);

  // BLE
  BLEDevice::init("MyoSignals");
  BLEDevice::setMTU(247);            // permite paquetes de 202 bytes
  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new ServerCB());
  BLEService *service = server->createService(SERVICE_UUID);
  emgChar = service->createCharacteristic(EMG_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  emgChar->addDescriptor(new BLE2902());
  service->start();
  // El anuncio tiene un maximo de 31 bytes: con el nombre + el UUID de 128 bits
  // no entra. Por eso el anuncio lleva solo el nombre y el UUID no se publica.
  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.println("Anunciando como 'MyoSignals'");

  // Timer de muestreo
  esp_timer_create_args_t args = {};
  args.callback = &sampleCb;
  args.name = "emg";
  esp_timer_handle_t timer;
  esp_timer_create(&args, &timer);
  esp_timer_start_periodic(timer, 1000000UL / FS);

  Serial.println("MyoSignals BLE listo");
}

void loop() {
  static uint8_t pkt[2 + 2 * BLOCK];
  static bool wasConnected = false;

  // Manejo de conexion: al desconectarse, esperar y volver a anunciar
  if (connected && !wasConnected) {
    Serial.println("Conectado");
    digitalWrite(LED_PIN, HIGH);
  }
  if (!connected && wasConnected) {
    Serial.println("Desconectado, vuelvo a anunciar");
    digitalWrite(LED_PIN, LOW);
    delay(500);                      // dar tiempo al stack BLE
    BLEDevice::startAdvertising();
  }
  wasConnected = connected;

  while (blocksSent < blocksWritten) {
    // Si el envio se atraso mas que el buffer, se saltean bloques
    // (la PC lo detecta por el numero de secuencia).
    if (blocksWritten - blocksSent > NBUF - 1) blocksSent = blocksWritten - (NBUF - 1);

    uint32_t b = blocksSent % NBUF;
    uint16_t seq = (uint16_t)blocksSent;
    pkt[0] = seq & 0xFF;
    pkt[1] = seq >> 8;
    for (int i = 0; i < BLOCK; i++) {
      pkt[2 + 2 * i] = buf[b][i] & 0xFF;
      pkt[3 + 2 * i] = buf[b][i] >> 8;
    }
    if (connected) {
      emgChar->setValue(pkt, sizeof(pkt));
      emgChar->notify();
    }
    blocksSent++;
  }
  delay(1);
}
