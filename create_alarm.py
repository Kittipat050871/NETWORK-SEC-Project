import numpy as np
from scipy.io.wavfile import write

# สร้างเสียง Beep 2 จังหวะ (จำลองไซเรน)
sample_rate = 44100
t = np.linspace(0., 1., sample_rate)
# ความถี่ 880Hz (โน้ต A5) และ 1000Hz 
siren_wave = np.sin(2. * np.pi * 880. * t) * (np.sin(2. * np.pi * 4 * t) > 0) + np.sin(2. * np.pi * 1000. * t) * (np.sin(2. * np.pi * 4 * t) < 0)

# บันทึกเป็นไฟล์ alarm.wav
write("alarm.wav", sample_rate, siren_wave.astype(np.float32))
print("สร้างไฟล์ alarm.wav สำหรับทดสอบเรียบร้อยแล้ว!")