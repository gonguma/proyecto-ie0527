# Virtual environment para Python
# python3 -m venv .venv
# source .venv/bin/activate

# Librería C de pigpio / Solo dentro de la Raspberry Pi
# sudo apt-get install pigpio

# Librería RF24 C++ (desde GitHub)
git clone https://github.com/nRF24/RF24.git
cd RF24
./configure
make
sudo make install