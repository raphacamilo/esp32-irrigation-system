import dht
import time
import network
import socket
from machine import Pin
import _thread


## Network Settings
ssid = ''
password = ''

# HTML Settings
maxLinesInHTML = 50
humTablehtml = ''
tempTableHtml = ''

class WebService:
    def __init__(self):
        self._ip_address = ''
    
    def connect(self):
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
    
        if not wlan.isconnected():
            print('connecting to network...')
            wlan.connect(ssid, password)
        
            while not wlan.isconnected():
                pass
        self._ip_address = wlan.ifconfig()[0]
        print('network ipv4:', self._ip_address)
    
    def createSocket(self):
        addr = socket.getaddrinfo(self._ip_address, 80)[0][-1]
        self._socket = socket.socket()
        self._socket.bind(addr)
        self._socket.listen(5)
        print('listening on ', addr)
        
    def listenClient(self):
        conn, addr = self._socket.accept()
        print('client connected from', addr)
        request = conn.recv(1024)
        request = str(request)
        
        if request.find('GET /humidity-table ') > 0:
            conn.send('HTTP/1.1 200 OK\n')
            conn.send('Content-Type: text/html\n')
            conn.send('Connection: close\n\n')        
            conn.sendall(humTablehtml)
        elif request.find('GET /temperature-table ') > 0:
            conn.send('HTTP/1.1 200 OK\n')
            conn.send('Content-Type: text/html\n')
            conn.send('Connection: close\n\n')        
            conn.sendall(tempTableHtml)
        else:
            conn.send('HTTP/1.1 200 OK\n')
            conn.send('Content-Type: application/json\n')
            conn.send('Connection: close\n\n')        
            conn.sendall("Page not found")
            
        conn.close()
        
class Storage:
    def __init__(self):
        self._humData = []
        self._tempData = []
    
    def getTimestamp(self):
        t = time.localtime()
        return '{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}'.format(t[0], t[1], t[2], t[3], t[4], t[5])
        
    def addHumidity(self, hum):
        status = 'OK'
        if hum < 20:
            status = 'Abaixo'
        elif hum > 85:
            status = 'Acima'

        self._humData.append({'humidity': hum, 'status': status, 'timestamp': self.getTimestamp()})

    def addTemperature(self, temperature):
        self._tempData.append({'temperature': temperature, 'timestamp': self.getTimestamp()})

    def storeData(self):
        print('storing data...')
        humFile = open('humidity.csv', 'a')
        for d in self._humData:
            humFile.write('{};{};{}\n'.format(d['humidity'], d['status'], d['timestamp']))
        
        self._humData = []
        humFile.close()

        tempFile = open('temperature.txt', 'a')
        for d in self._tempData:
            tempFile.write('{},{}\n'.format(d['temperature'], d['timestamp']))
        
        self._tempData = []
        tempFile.close()
        print('finished storing data')
        
    def getFullHTML(self, htmlPage, file):
        lineCounter = 0
        data = []
        with open(htmlPage, "r") as fd:
            htmlTemplate = fd.read()
            
            with open(file, 'r') as f:
                for line in reversed(list(f)):
                    if lineCounter >= maxLinesInHTML:
                        break
                    lineCounter += 1
                    data.append('"{}"'.format(line.strip()))
                    
            return htmlTemplate.replace('"ESP32FileData"', ','.join(data))
        
    def createHumTableHTML(self):
        global humTablehtml
        humTablehtml = self.getFullHTML("humidity-table.html", "humidity.csv")

    def createTempTableHTML(self):
        global tempTableHtml
        tempTableHtml = self.getFullHTML("temperature-table.html", "temperature.txt")


class Sensor:
  def __init__(self, pin_number):
    self._dht_sensor = dht.DHT11(Pin(pin_number))

  def getData(self):
    self._dht_sensor.measure()
    return (self._dht_sensor.temperature(), self._dht_sensor.humidity())

class Led:
  def __init__(self, pin_number):
    self._led = Pin(pin_number, Pin.OUT)
    self._led.value(0)

  def blink(self, times=1):
    led_value = 1
    for _ in range(2*times):
      self._led.value(led_value)
      led_value = 1 if led_value == 0 else 0
      time.sleep(0.2)


class Controller:
  def __init__(self, sensor, led_hum, led_temp, web_service, store):
    self.sensor = sensor
    self.led_hum = led_hum
    self.led_temp = led_temp
    self.web_service = web_service
    self.store = store
    self.storeIterator = 0
    
  def getSensorData(self):
   return self.sensor.getData()

  def ledFeedback(self, hum, temp):
    if hum < 30:
      self.led_hum.blink(2)
    elif hum <= 50:
      self.led_hum.blink(3)
    else:
      self.led_hum.blink(4)
    
    if temp < 10:
      self.led_temp.blink(2)
    elif temp < 30:
      self.led_temp.blink(3)
    else:
      self.led_temp.blink(4)

  def dataThread(self):
    while True:
        print('starting data response')
        data = self.getSensorData()
        self.ledFeedback(data[1], data[0])
        
        if self.storeIterator >= 15:
            self.storeIterator = 0
            self.store.addHumidity(data[1])
            self.store.addTemperature(data[0])
            
            self.store.storeData()
            self.store.createHumTableHTML()
            self.store.createTempTableHTML()
        
        self.storeIterator += 1
        print('finished data response')
        time.sleep(0.5)
        

  def webThread(self):
    while True:
        self.web_service.listenClient()
        
  def run(self):
    self.web_service.connect()
    self.web_service.createSocket()
    self.store.createHumTableHTML()
    self.store.createTempTableHTML()
    
    _thread.start_new_thread(self.dataThread, ())
    self.webThread()


sensor = Sensor(5)
led_hum = Led(18)
led_temp = Led(21)
web_service = WebService()
store = Storage()

controller = Controller(sensor, led_hum, led_temp, web_service, store)
controller.run()