import time
import serial
import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Date, Boolean, event
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# 1. Install the required packages
# pip install sqlalchemy mysql-connector-python pyserial

# 2. Set up the MySQL connection and SQLAlchemy configuration
db_url = "mysql+pymysql://root:pass@192.168.5.225:3306/pms"
engine = create_engine(db_url)
Base = declarative_base()
Session = sessionmaker(bind=engine)
session = Session()

# 2.  Define your classes
# Encounter Class -----------------------------------------------------------------------------------------------------------
class Encounter(Base):

    __tablename__ = "encounter"
    encounter_id = Column(Integer(), primary_key=True, autoincrement=True)
    patient_id = Column(Integer(), ForeignKey("patient.patient_id"))
    rdv = Column(DateTime())
    notified = Column(Boolean, default=False)
    note = Column(String(100), default='')
    payment = Column(Integer(), default=0)
    treatment_cost = Column(Integer(), default=0)
    patient = relationship("Patient", back_populates="encounters")

    def __repr__(self):
        return f'{self.encounter_id},{self.rdv},{self.note},{self.payment},{self.treatment_cost}'

# Patient Class -----------------------------------------------------------------------------------------------------------
class Patient(Base):

    __tablename__ = 'patient'
    patient_id = Column(Integer(), primary_key=True, autoincrement=True)
    first_name = Column(String(50))
    last_name = Column(String(50))
    phone = Column(Integer())
    date_of_birth = Column(Date())
    encounters = relationship("Encounter")

    def __repr__(self):
        return f'{self.patient_id},{self.first_name},{self.last_name},{self.date_of_birth},{self.phone}'

#---------------------------------------------------------------------------------------------------------------------------

# 3. Create the SMS sending function using the modem and AT commands


def send_sms(phone_number, message):
    # Convert phone number and message to UCS2 hex format
    ucs2_phone_number = phone_number.encode("utf-16be").hex()
    ucs2_message = message.encode("utf-16be").hex()

    # Set up the serial connection
    ser = serial.Serial('/dev/serial0', 9600, timeout=1)
    ser.flushInput()
    ser.flushOutput()

    # Set character set to UCS2 encoding
    ser.write(b'AT+CSCS="UCS2"\r')
    time.sleep(0.5)
    ser.write(b'AT+CSMP=17,167,0,8\r')
    time.sleep(2)
    # Set modem to text mode
    ser.write(b'AT+CMGF=1\r')
    time.sleep(0.5)

    # Send SMS
    send_cmd = f'AT+CMGS="{ucs2_phone_number}"\r\n'
    ser.write(send_cmd.encode())
    time.sleep(0.5)

    ser.write(ucs2_message.encode() + b'\x1A')  # Add the <CTRL-Z> character (ASCII 26)
    time.sleep(7)

    # response = ser.read(ser.in_waiting)
    ser.close()

    # if b"+CMGS" in response:
    #     print("Message sent successfully!")
    # else:
    #     print("Failed to send the message.")
    

def send_sms_for_new_encounters():
    now = datetime.datetime.now()
    one_day_later = now + datetime.timedelta(days=1)
    new_encounters = session.query(Encounter).join(Patient).filter(Encounter.rdv.between(now, one_day_later), Encounter.notified == False).all()

    print(new_encounters)
    for encounter in new_encounters:
        if not encounter.notified:
            patient = encounter.patient
            message = f"السيد/ة {patient.first_name} {patient.last_name}، نود تذكيركم بموعدكم في عيادتنا اليوم في تمام الساعة {encounter.rdv.strftime('%H:%M')}. نتطلع لرؤيتكم ونأمل أن تكونوا بأفضل حال. دمتم بخير!"
            # message = f"Dear {patient.first_name} {patient.last_name}, you have an appointment tomorrow at {encounter.rdv.strftime('%H:%M')}. Please, don't be late."
            sent = send_sms(f'+213{patient.phone}', message)
            #if sent:
            print(f"SMS sent to {patient.first_name} {patient.last_name} for appointment at {encounter.rdv.strftime('%H:%M')}.")
            encounter.notified = True
            session.commit()
            #else:
            #    print(f"Failed to send SMS to {patient.first_name} {patient.last_name} for appointment at {encounter.rdv.strftime('%H:%M')}.")


if __name__ == "__main__":
    send_sms_for_new_encounters()



