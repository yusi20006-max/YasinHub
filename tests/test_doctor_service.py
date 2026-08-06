from yasinhub.services.doctor_service import DoctorService


def main():

    doctor = DoctorService()

    print(doctor.run())


if __name__ == "__main__":
    main()
