import adafruit_dht
import board
import time

# Initialize the DHT sensor on GPIO4
dht_device = adafruit_dht.DHT11(board.D4)

# File to store sensor data
file_path = "/home/hossam/proj2/dht_data.txt"

while True:
    try:
        # Read temperature and humidity
        temperature = dht_device.temperature
        humidity = dht_device.humidity

        # Write data to a file
        with open(file_path, "w") as f:
            f.write(f"{temperature},{humidity}")

    except Exception as e:
        with open(file_path, "w") as f:
            f.write(f"Error: {e}")

    time.sleep(2)  # Update every 2 seconds

