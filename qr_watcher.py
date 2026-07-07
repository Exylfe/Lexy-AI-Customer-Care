"""
Watch for qr.txt and generate a clean QR image + HTML page.
Run this alongside the WhatsApp bridge.
"""
import os
import time
import qrcode

QR_FILE = os.path.join(os.path.dirname(__file__), "whatsapp-bridge", "qr.txt")
QR_PNG = os.path.join(os.path.dirname(__file__), "whatsapp-bridge", "qr.png")
QR_HTML = os.path.join(os.path.dirname(__file__), "whatsapp-bridge", "qr.html")

print("Waiting for QR code from WhatsApp bridge...")

while not os.path.exists(QR_FILE):
    time.sleep(1)

with open(QR_FILE) as f:
    data = f.read().strip()

# Generate PNG
img = qrcode.make(data)
img.save(QR_PNG)
print(f"QR image saved: {QR_PNG}")

# Generate HTML with clean display
html = f"""<!DOCTYPE html>
<html>
<head><title>Lexy WhatsApp QR</title></head>
<body style="display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#fff">
<div style="text-align:center">
  <h2 style="font-family:sans-serif;color:#333">Scan with WhatsApp</h2>
  <img src="qr.png" alt="QR Code" style="max-width:400px;image-rendering:pixelated">
  <p style="font-family:sans-serif;color:#666">Open WhatsApp → Linked Devices → Link a Device</p>
</div>
</body>
</html>"""

with open(QR_HTML, "w") as f:
    f.write(html)
print(f"QR HTML page: {QR_HTML}")
print("Open the HTML file in your browser and scan with your phone.")
