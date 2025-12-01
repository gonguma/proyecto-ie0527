#!/usr/bin/env python3
import struct
import zlib
from pathlib import Path
import time
import sys

import RPi.GPIO as GPIO
from pyrf24 import RF24, RF24_PA_MAX, RF24_250KBPS, RF24_DRIVER

# ----------------- Pines (BCM) -----------------
LED1 = 17       # LED verde (estado general / idle)
LED2 = 27       # LED amarillo (modo RX)

# nRF24
CE_PIN = 22     # CE -> GPIO22 (pin físico 15)
CSN_PIN = 0     # CSN = 0 -> /dev/spidev0.0 (CE0)

# Dirección RF (igual que en Arduino: "00001")
ADDRESS = b"00001"

# Crear objeto radio (global)
radio = RF24(CE_PIN, CSN_PIN)

CHUNK_SIZE = 32          # tamaño de payload del nRF24
HEADER_PREFIX = b"HDR"   # prefijo de cabecera

# ----------------- GPIO -----------------
def setup_gpio():
    GPIO.setmode(GPIO.BCM)

    # LEDs como salida
    GPIO.setup(LED1, GPIO.OUT)
    GPIO.setup(LED2, GPIO.OUT)

    # LEDs apagados al inicio
    GPIO.output(LED1, GPIO.LOW)
    GPIO.output(LED2, GPIO.LOW)


# ----------------- RF24 -----------------
def setup_radio():
    print("RF24_DRIVER =", RF24_DRIVER)
    print(f"Inicializando radio en CE={CE_PIN}, CSN={CSN_PIN} (/dev/spidev0.0)")

    if not radio.begin():
        print("Error iniciando el radio RF24 (radio.begin() devolvió False).")
        print("Revisa: SPI habilitado, CE/CSN/SCK/MOSI/MISO, VCC=3.3V y GND común.")
        sys.exit(1)

    # Configuración de radio (igual que Arduino de ejemplo)
    radio.setPALevel(RF24_PA_MAX)       # potencia de salida
    radio.setChannel(108)               # canal (0-125)
    radio.setDataRate(RF24_250KBPS)     # data rate
    radio.setAutoAck(True)
    radio.setRetries(5, 15)

    # Solo RX: abrimos un pipe de lectura
    radio.openReadingPipe(1, ADDRESS)

    # Arrancamos en modo escucha
    radio.startListening()

    # Info opcional
    print("Radio inicializado correctamente.")
    try:
        print("radio.is_chip_connected =", radio.is_chip_connected)
    except Exception:
        pass


# ----------------- Utilidad: parpadeo de error -----------------
def blink_error(times=3, delay=0.2):
    for _ in range(times):
        GPIO.output(LED1, GPIO.LOW)
        GPIO.output(LED2, GPIO.HIGH)
        time.sleep(delay)
        GPIO.output(LED1, GPIO.HIGH)
        GPIO.output(LED2, GPIO.LOW)
        time.sleep(delay)


# ----------------- RX: recibir y guardar archivo -----------------
def receive_file_over_radio(dest_path, header_timeout_s=10, data_timeout_s=2):
    """
    Recibe un archivo vía nRF24 y lo guarda en dest_path.
    LED1 apagado, LED2 encendido mientras espera/recibe.
    Devuelve True si todo salió bien, False si hubo error.
    """
    print(f"[RX] Guardará archivo en: {dest_path}")

    # LEDs: LED1 OFF, LED2 ON
    GPIO.output(LED1, GPIO.LOW)
    GPIO.output(LED2, GPIO.HIGH)

    radio.startListening()

    # 1) Esperar cabecera
    print(f"[RX] Esperando cabecera (timeout {header_timeout_s} s)...")
    start = time.time()
    file_size = None
    crc_expected = None

    while True:
        if radio.available():
            packet = radio.read(CHUNK_SIZE)
            if not packet.startswith(HEADER_PREFIX):
                print("[RX] Paquete sin 'HDR' ignorado.")
                continue

            try:
                file_size, crc_expected = struct.unpack("<II", packet[3:11])
            except struct.error:
                print("[RX] ERROR: cabecera mal formada.")
                radio.stopListening()
                GPIO.output(LED2, GPIO.LOW)
                return False

            print(f"[RX] Cabecera: tamaño={file_size} bytes, CRC32={crc_expected:08X}")
            break

        if time.time() - start > header_timeout_s:
            print("[RX] ERROR: timeout esperando cabecera.")
            radio.stopListening()
            GPIO.output(LED2, GPIO.LOW)
            return False

        time.sleep(0.01)

    # 2) Recibir datos
    print("[RX] Recibiendo datos...")
    received = bytearray()
    last_rx = time.time()

    while len(received) < file_size:
        if radio.available():
            chunk = radio.read(CHUNK_SIZE)
            received.extend(chunk)
            last_rx = time.time()
        else:
            if time.time() - last_rx > data_timeout_s:
                print("[RX] ERROR: timeout recibiendo datos.")
                radio.stopListening()
                GPIO.output(LED2, GPIO.LOW)
                return False
            time.sleep(0.005)

    radio.stopListening()

    # Recortar al tamaño exacto
    data = bytes(received[:file_size])

    # Verificar CRC
    crc_calc = zlib.crc32(data) & 0xFFFFFFFF
    if crc_calc != crc_expected:
        print(f"[RX] ERROR CRC: esperado {crc_expected:08X}, calculado {crc_calc:08X}")
        GPIO.output(LED2, GPIO.LOW)
        return False

    # Guardar archivo
    dest_path.write_bytes(data)
    print(f"[RX] Archivo recibido y guardado correctamente ({file_size} bytes).")

    # LEDs: LED2 OFF, LED1 ON
    GPIO.output(LED2, GPIO.LOW)
    GPIO.output(LED1, GPIO.HIGH)

    return True


# ----------------- Modo RX en bucle -----------------
def modo_rx_loop():
    """
    Bucle infinito en modo RX:
    - LED1 encendido indica "listo / idle".
    - Cuando se recibe un archivo, se guarda como recibido.txt en esta carpeta.
    - Tras cada intento (éxito o error), vuelve a estado idle.
    """
    base_dir = Path(__file__).resolve().parent
    dest_path = base_dir / "recibido.txt"

    while True:
        # Estado idle
        GPIO.output(LED1, GPIO.HIGH)
        GPIO.output(LED2, GPIO.LOW)
        print("\n[MAIN] Listo para recibir. LED1 encendido.")
        print("[MAIN] Esperando archivo...")

        ok = receive_file_over_radio(dest_path,
                                     header_timeout_s=60,
                                     data_timeout_s=2)

        if not ok:
            print("[MAIN] Intento de recepción fallido.")
            blink_error()
        else:
            print("[MAIN] Recepción OK. Archivo guardado.")

        # Pequeña pausa antes de esperar otra vez
        time.sleep(1)


# ----------------- Programa principal -----------------
def main():
    setup_gpio()
    setup_radio()
    modo_rx_loop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSaliendo por Ctrl+C...")
    finally:
        GPIO.cleanup()
