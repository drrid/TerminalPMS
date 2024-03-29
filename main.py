from textual.app import App
from textual.screen import Screen, ModalScreen
from textual.widgets import Static, Footer, Header, Input, DataTable, Button, RadioButton, RadioSet, SelectionList, RichLog, ProgressBar
from textual.coordinate import Coordinate
from textual.containers import Container, Horizontal, Vertical, VerticalScroll, Grid
from textual.reactive import reactive
from textual import work
import conf
import datetime as dt
from dateutil import parser
import asyncio
import os
from natsort import natsorted 
import re
from sys import platform
from rich.text import Text

import subprocess
import select


import paramiko
from dotenv import load_dotenv
from textual.worker import Worker, get_current_worker
import time as tm

if platform == 'win32':
    import ctypes

from datetime import date, timedelta

import shutil
import subprocess


load_dotenv()
passkey = os.getenv('PASSKEY')
host = os.getenv('HOST')
special_account = os.getenv('SPECIAL_ACCOUNT')
ubuntu_pass = os.getenv('UBUNTU_PASS')


# Printing Export Screen --------------------------------------------------------------------------------------------------------------------------------------------------
class PrintExportScreen(ModalScreen):

    nb_aligners = []
    worker = []
    split_selected_files = []
    to_print = []
    
    def compose(self):
        self.selectionlist = SelectionList[int]()
        with Grid(id='dialog'):
            with Horizontal(id='selection'):
                with Vertical(id='right_cnt'):
                    with RadioSet(id='exports'):
                        yield RadioButton('3D models', id='models', value=True)
                        yield RadioButton('Prescription', id='prescription')
                        # yield RadioButton('custom', id='custom')
                        # yield RadioButton('patient', id='pt-select')
                    yield Button('toggle all', id='toggle-all')
                    yield(Static(id='feedback_popup'))
                with VerticalScroll(id='printjobs'):
                    yield self.selectionlist
            with Horizontal(id='progress-pane'):
                yield(ProgressBar(id='progress', total=100))
            with Horizontal():
                yield(RichLog(id='textlog', highlight=True, markup=True, wrap=True))
            with Horizontal(id='buttons'):
                yield Button('export', id='export', variant='primary')
                yield Button('print', id='print', variant='primary')
                yield Button('exit', id='exit', variant='error')


    def on_mount(self):
        self.show_selectionlist()

    def show_selectionlist(self):
        try:
            self.selectionlist.clear_options()
            selected_radio = self.query_one('#exports').pressed_button.id

            if selected_radio == 'models':
                calendar_screen: Calendar = self.app.SCREENS.get('calendar')
                patient = calendar_screen.patient_widget.get_row_at(calendar_screen.patient_widget.cursor_coordinate.row)
                patient_long_id = f'{patient[0]} {patient[1]} {patient[2]}'
                self.selectionlist.border_title = patient_long_id

                if platform == 'darwin':
                    pt_dir = f'/Volumes/mediaserver/patients/{patient_long_id}'
                else:
                    pt_dir = f'Z:\\patients\\{patient_long_id}'

                self.nb_aligners = []
                scanned_files = os.listdir(pt_dir)

                for file in natsorted(scanned_files):
                    if file.endswith(f'.stl'):
                        self.nb_aligners.append(file)
                        self.selectionlist.add_option((file.split('_')[-1], file))
                if len(self.nb_aligners) == 0:
                    self.log_feedback('no STL files found!')

            elif selected_radio == 'prescription':
                self.selectionlist.add_option(('Pano', 'pano'))
                self.selectionlist.add_option(('Teleradiographie', 'tlr'))
                self.selectionlist.add_option(('Pano + Teleradiographie', 'pano_tlr'))
                self.selectionlist.add_option(('Certificat', 'certificat'))
                self.selectionlist.add_option(('Empty', 'empty'))

        except Exception as e:
            self.log_error('Error in show_selectionlist: ' + str(e))


    def on_radio_set_changed(self, event: RadioSet.Changed):
        self.show_selectionlist()


    def on_worker_state_changed(self, event: Worker.StateChanged):
        # self.log_feedback('Running')
        for worker in self.workers:
            if worker.is_finished:
                self.worker.append(worker)

        if len(self.worker) == len(self.split_selected_files):
                # self.log_feedback('finished all')
                self.cleanup()
        

    def on_button_pressed(self, event: Button.Pressed):
        try:
            self.worker = []
            self.split_selected_files = []
            self.to_print = []

            selected_radio = self.query_one('#exports').pressed_button.id
            if selected_radio == 'models':
                calendar_screen: Calendar = self.app.SCREENS.get('calendar')
                patient = calendar_screen.patient_widget.get_row_at(calendar_screen.patient_widget.cursor_coordinate.row)

                selected_files = []
                for file in self.selectionlist.selected:
                    filepath = f'/home/tarek/zfsmedia2/patients/{patient[0]} {patient[1]} {patient[2]}/{file}'
                    selected_files.append(filepath)

                split_selected_files = [selected_files[i:i + 10] for i in range(0, len(selected_files), 10)]  
                timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                self.split_selected_files = split_selected_files

                if event.button.id == "export":
                    destination_flash_drive = self.get_flash_drive_path_by_name('TAREK')
                    self.delete_files_in_directory(destination_flash_drive)
                
                    client = self.connect_to_server()
                    for i, chunk in enumerate(split_selected_files):
                        client = self.connect_to_server()
                        self.query_one('#progress').update(progress=0)
                        pt_name = f"'/home/tarek/zfsmedia2/patients/{patient[0]} {patient[1]} {patient[2]}/{len(selected_files)}-{timestamp}-{i}.sl1'"


                        if platform == 'darwin':
                            pt_name_final = os.path.join(f"/Volumes/mediaserver/patients/{patient[0]} {patient[1]} {patient[2]}/", f'{len(selected_files)}-{timestamp}-{i}.pm3')
                        else:
                            pt_name_final = f'Z:\\patients\\{patient[0]} {patient[1]} {patient[2]}\\{len(selected_files)}-{timestamp}-{i}.pm3'

                        self.to_print.append(pt_name_final)

                        chunck_joined = "' '".join(chunk)

                        prusa_cmd = "prusa-slicer --export-sla --merge --load config.ini --output"
                        uvtools_cmd =  '/home/tarek/uvtools/UVtoolsCmd convert'
                        command = f"{prusa_cmd} {pt_name} '{chunck_joined}' && {uvtools_cmd} {pt_name} pm3"
                        self.slice(client=client, command=command)

                elif event.button.id == "print":
                    self.print_pt(patient, len(selected_files)/2, self.get_onyxceph_link(patient))

                elif event.button.id == 'toggle-all':
                    if len(self.selectionlist.selected) == self.selectionlist.option_count:
                        self.selectionlist.deselect_all()
                    else:
                        self.selectionlist.select_all()

                elif event.button.id == "exit":
                    self.app.pop_screen()


            elif selected_radio == 'prescription':
                calendar_screen: Calendar = self.app.SCREENS.get('calendar')
                patient = calendar_screen.patient_widget.get_row_at(calendar_screen.patient_widget.cursor_coordinate.row)

                if event.button.id in ["export", "print"]:
                    for selection in self.selectionlist.selected:
                        result = conf.generate_prescription_png(patient, selection)
                        if result:
                            self.log_error(result)
                        if event.button.id == "print":
                            # On Windows
                            try:
                                import win32print
                                win32print.SetDefaultPrinter(win32print.GetDefaultPrinter())
                                file_path = os.path.join(f'Z:\\patients\\{patient[0]} {patient[1]} {patient[2]}\\', f'{selection}.png')
                                os.startfile(file_path, 'print')
                            except ImportError:
                                print("win32print module not found. Ensure you have installed pypiwin32.")

                elif event.button.id == "exit":
                    self.app.pop_screen()
        
        except Exception as e:
            self.log_error(str(e))


    def connect_to_server(self):
        client = paramiko.SSHClient()
        policy = paramiko.AutoAddPolicy()
        client.set_missing_host_key_policy(policy)
        client.connect(host, username=special_account, password=ubuntu_pass)
        return client
    

    @work(exclusive=False, thread=True)
    def slice(self, client, command):
        try:
            stdin, stdout, stderr = client.exec_command(command, get_pty=True)
            self.query_one('#textlog').write(f'[bold teal]executing {command}')
            for line in iter(stdout.readline, ""):
                match = re.finditer(r'\d+(\.\d+)?%', line)
                self.app.call_from_thread(self.query_one('#textlog').write ,line)
                # self.query_one('#textlog').write(line)
                if match:
                    for pr in match:
                        progress = round(float(pr.group()[0:-1]))
                        self.app.call_from_thread(self.update_progress ,progress)
            client.close()
        except Exception as e:
            self.log_error(str(e))


    @work(exclusive=False, thread=True)
    def cleanup(self):
        try:
            client = self.connect_to_server()
            calendar_screen: Calendar = self.app.SCREENS.get('calendar')
            patient = calendar_screen.patient_widget.get_row_at(calendar_screen.patient_widget.cursor_coordinate.row)
            command = f"cd '/home/tarek/zfsmedia2/patients/{patient[0]} {patient[1]} {patient[2]}/' && rm *.sl1"

            stdin, stdout, stderr = client.exec_command(command, get_pty=True)
            self.query_one('#textlog').write(f'[bold teal]executing {command}')
            for line in iter(stdout.readline, ""):
                match = re.finditer(r'\d+(\.\d+)?%', line)
                self.app.call_from_thread(self.query_one('#textlog').write ,line)

            client.close()

            for i, file_to_print in enumerate(self.to_print):
                self.copy_file_to_flash_drive(file_to_print, 'TAREK', f'{os.path.basename(file_to_print)}')
            
        except Exception as e:
            self.log_error(str(e))


    def print_pt(self, patient, nb_models, link):
        with open(f'C:\\Users\\tarek\\OneDrive\\Documents\\bt\\{patient[0]}.txt', 'w') as pt_file:
            pt_file.write('ptID,ptFName,ptLName,UL,nbModels' + '\n')
            pt_file.write(f'{patient[0]},{patient[1]},{patient[2]},Lower,{nb_models}')

        with open(f'C:\\Users\\tarek\\OneDrive\\Documents\\bt\\{patient[0]}2.txt', 'w') as pt_file:
            pt_file.write('ptID,ptFName,ptLName,UL,nbModels' + '\n')
            pt_file.write(f'{patient[0]},{patient[1]},{patient[2]},Upper,{nb_models}')

        with open(f'C:\\Users\\tarek\\OneDrive\\Documents\\bt2\\{patient[0]}.txt', 'w') as pt_file:
            pt_file.write('ptFName,ptLName,link' + '\n')
            pt_file.write(f'{patient[1]},{patient[2]},{link}')


    def get_onyxceph_link(self, patient):
        try:
            base = 'https://onyxceph.tarekserver.me/'

            if platform == 'darwin':
                root_path = f'/Volumes/mediaserver/onyx-animation/clients/Client0/{patient[0]}'
            else:
                root_path = f'Z:\\onyx-animation\\clients\\Client0\\{patient[0]}'

            for dirpath, _, file in os.walk(root_path):
                for f in file:
                    if f.endswith('.iiwgl'):
                        url = f'{base}?mlink={base}clients/Client0/{patient[0]}/{f}&fg=088&bg=134&p=pms'
                        self.log_feedback(url)
                        return url
        except Exception as e:
            self.log_error('Error in get_onyxceph_link' + str(e))
          
    
    def update_progress(self, progress):
        try:
            self.query_one('#progress').update(progress=progress)
        except Exception as e:
            self.log_error(str(e))


    def log_feedback(self, msg):
        self.query_one('#feedback_popup').update(f'[bold #11696b]{str(msg)}')

    def log_error(self, msg):
        self.query_one('#feedback_popup').update(f'[bold red]{str(msg)}')


    def get_flash_drive_path_by_name(self, name):
        if platform == "win32":
            cmd = f'wmic logicaldisk where "VolumeName=\'{name}\'" get caption'
            output = subprocess.check_output(cmd, shell=True).decode().strip()
            if len(output) > 1:
                return output.split('\n')[1].strip()
        else:
            cmd = 'df -H | grep "/Volumes/{}"'.format(name)
            output = subprocess.check_output(cmd, shell=True).decode().strip()
            if output:
                return output.split()[0]
        return None

    def delete_files_in_directory(self, directory):
        try:
            for filename in os.listdir(directory):
                file_path = os.path.join(directory, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    self.query_one('#textlog').write(f"Deleted: {filename}")
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                    self.query_one('#textlog').write(f"Deleted directory: {filename}")
            self.query_one('#textlog').write("All files deleted successfully.")
        except Exception as e:
            self.query_one('#textlog').write(f"An error occurred while deleting files: {str(e)}")


    def copy_file_to_flash_drive(self, source_file_path, destination_flash_drive_name, new_file_name):
        try:
            # Check if the source file exists
            if not os.path.exists(source_file_path):
                self.query_one('#textlog').write("Source file does not exist." + source_file_path)
                return

            # Get the mount point of the destination flash drive
            destination_flash_drive = self.get_flash_drive_path_by_name(destination_flash_drive_name)
            if not destination_flash_drive:
                self.query_one('#textlog').write(f"Flash drive with name '{destination_flash_drive_name}' not found.")
                return
            self.query_one('#textlog').write(destination_flash_drive)
            # Remove all files from the flash drive
            # self.delete_files_in_directory(destination_flash_drive)

            # Combine the destination path with the new file name
            destination_path = os.path.join(destination_flash_drive, new_file_name)

            # Copy the file to the flash drive
            shutil.copy2(source_file_path, destination_path)

            self.query_one('#textlog').write("File copied successfully.")
        except Exception as e:
            self.query_one('#textlog').write(f"An error occurred: {str(e)}")



# Calendar Screen --------------------------------------------------------------------------------------------------------------------------------------------------
class Calendar(Screen):
    BINDINGS = [("ctrl+left", "previous_week", "Previous Week"),
            ("ctrl+right", "next_week", "Next Week"),
            ("f1", "add_encounter", "Add Encounter"),
            ("f2", "modify_patient", "Modify Patient"),
            ("ctrl+delete", "delete_encounter", "Delete Encounter"),
            ("f5", "clear_inputs", "Clear"),
            ("f10", "request_export", "Export")]
    week_index = reactive(0)
    row_index_id = {}
    row_index_enc_id = {}
    modify_pt = False


    def compose(self):
        self.table = DataTable()
        self.calendar_widget = DataTable(id='cal_table', fixed_columns=1, zebra_stripes=True)
        self.encounter_widget = DataTable(id='enc_table', zebra_stripes=True, fixed_columns=1)
        self.patient_widget = DataTable(id='pt_table', zebra_stripes=True, fixed_columns=1)
        self.patient_widget.cursor_type = 'row'

        self.inputs_container = Vertical(Horizontal(
                                    Input('', placeholder='First Name', id='fname'),Input('', placeholder='Last Name', id='lname'),
                                    Input('', placeholder='Date Of Birth', id='dob'), Input('', placeholder='Phone', id='phone'),
                                    Button('Add', id='addpatient'),Button('Update', id='updatepatient'), id='inputs'),
                                id='upper_cnt')
        self.tables_container = Vertical(
                            Horizontal(
                                Vertical(self.patient_widget,
                                        self.encounter_widget,
                                        Input(placeholder='Notes...', id='notes'), 
                                        RichLog(id='feedback', highlight=True, markup=True, wrap=True),
                                        id='tables'),
                                        self.calendar_widget,
                                id='tables_cnt'),
                            id='lower_cnt')
        
        self.footer_widget = Footer()
        self.footer_widget.styles.background = '#11696b'

        yield Header()
        yield Container(self.inputs_container, self.tables_container, id='app_grid')
        yield self.footer_widget    
    
    async def update_calendar_periodically(self) -> None:
        while True:
            await asyncio.sleep(10)  # Update every 10 seconds
            self.show_calendar(self.week_index)
            self.show_patients()

    def on_mount(self):
        if platform == 'win32':
            user32 = ctypes.windll.user32
            screensize = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
            # self.log_feedback(screensize)

        asyncio.create_task(self.update_calendar_periodically())

        PT_CLMN = [['ID', 3], ['First Name', 13], ['Last Name', 13], ['Date of Birth', 12], ['Phone', 10], ['Owed', 10]]
        for c in PT_CLMN:
            self.patient_widget.add_column(f'{c[0]}', width=c[1])

        ENC_CLMN = [['ID', 3], ['Encounter', 12], ['Note', 23], ['Payment', 7], ['Fee', 7]]
        for c in ENC_CLMN:
            self.encounter_widget.add_column(f'{c[0]}', width=c[1])


        self.show_calendar(self.week_index)
        self.show_patients()
        self.show_encounters()


    def on_input_submitted(self, event: Input.Submitted):
        try:
            cursor = self.encounter_widget.cursor_coordinate
            encounter_id = self.encounter_widget.get_cell_at(Coordinate(cursor.row,0))
            input_to_modify = self.query_one('#notes').value

            if cursor.column == 2:
                conf.update_encounter(encounter_id, note=str(input_to_modify))
                self.encounter_widget.update_cell_at(cursor, input_to_modify)
            if cursor.column == 3:
                conf.update_encounter(encounter_id, payment=int(input_to_modify))
                self.encounter_widget.update_cell_at(cursor, input_to_modify)
                self.show_patients()
            if cursor.column == 4:
                conf.update_encounter(encounter_id, treatment_cost=int(input_to_modify))
                self.encounter_widget.update_cell_at(cursor, input_to_modify)
                self.show_patients()
        except Exception as e:
            self.log_error(f"Error updating encounter: {e}")


    def on_input_changed(self, event: Input.Changed):
        if event.input.id != 'notes':
            try:
                fname = self.query_one('#fname').value
                lname = self.query_one('#lname').value
                phone = self.query_one('#phone').value
                if phone.isdigit():
                    phone = int(phone)
                else:
                    self.query_one('#phone').value = ''

                patients = conf.select_all_starts_with(first_name=fname, last_name=lname, phone=phone)
                if len(patients) != 0:
                    patient_id = patients[0][0]
                    row_index = self.row_index_id.get(patient_id)
                    self.patient_widget.move_cursor(row=row_index)
                    self.show_encounters()

            except Exception as e:
                self.log_error(e)


    def action_clear_inputs(self):
        for input in self.query(Input):
            input.value = ''


    def on_button_pressed(self, event: Button.Pressed):

        try:
            first_name = self.query_one('#fname').value.capitalize()
            last_name = self.query_one('#lname').value.capitalize()
            phone = self.query_one('#phone').value
            date_of_birth = self.query_one('#dob').value
        except Exception as e:
            self.log_error("Error occurred while fetching input values: " + str(e))
            return

        # Validate the input values
        if not first_name or not last_name or not phone or not date_of_birth:
            self.log_error("Please fill in all fields.")
            return

        try:
            parsed_dob = parser.parse(date_of_birth).date()
        except ValueError:
            self.log_error("Invalid date format. Please use YYYY-MM-DD format.")
            return

        try:
            parsed_phone = int(phone)
        except ValueError:
            self.log_error("Invalid phone number. Please enter a valid integer.")
            return

        # Check for patient duplication
        try:
            existing_patient = conf.select_patient_by_details(first_name, last_name, parsed_phone, parsed_dob)
            if existing_patient:
                self.log_error("Patient with the same details already exists.")
                return
        except Exception as e:
            self.log_error("Error occurred while checking for existing patient: " + str(e))
            return

        try:
            if event.control.id == 'addpatient':
                self.add_patient(first_name, last_name, parsed_phone, parsed_dob)
            elif event.control.id == 'updatepatient':         
                cursor = self.patient_widget.cursor_coordinate
                patient_id = self.patient_widget.get_cell_at(Coordinate(cursor.row, 0))
                self.update_patient(patient_id, first_name, last_name, parsed_phone, parsed_dob)
            else:
                self.log_error("Invalid button event.")
                return
        except Exception as e:
            self.log_error("Error occurred while performing patient action: " + str(e))
            return


    def action_delete_encounter(self):
        try:
            cursor = self.calendar_widget.cursor_coordinate
            patient_name = self.calendar_widget.get_cell_at(cursor)
            if '_' in patient_name:
                self.log_error('No encounter to delete!')
                return
            
            encounter_time = self.get_datetime_from_cell(self.week_index, cursor.row, cursor.column)
            encounter_id = conf.select_encounter_by_rdv(encounter_time).encounter_id
            conf.delete_encounter(encounter_id)
            self.calendar_widget.update_cell_at(cursor, '_')
            self.encounter_widget.clear()
            self.log_feedback('Encounter deleted successfully.')
        except Exception as e:
            self.log_error("Error occurred on delete_encounter: " + str(e))


    def action_add_encounter(self):
        try:
            cursor = self.calendar_widget.cursor_coordinate
            cursor_value = self.calendar_widget.get_cell_at(cursor)
            if '_' not in cursor_value:
                self.log_error(f"Time slot occupied, please choose another one!")
                return
            
            patient_id = int(self.patient_widget.get_cell_at(Coordinate(self.patient_widget.cursor_coordinate.row, 0)))
            patient_first_name = self.patient_widget.get_cell_at(Coordinate(self.patient_widget.cursor_coordinate.row, 1))
            patient_last_name = self.patient_widget.get_cell_at(Coordinate(self.patient_widget.cursor_coordinate.row, 2))

            selected_datetime = self.get_datetime_from_cell(self.week_index, cursor.row, cursor.column)
            conf.save_to_db(conf.Encounter(patient_id=patient_id, rdv=selected_datetime))

            self.calendar_widget.update_cell_at(cursor, f'{patient_first_name} {patient_last_name}')
            self.encounter_widget.clear()
            # self.show_encounters(patient_id)
            self.log_feedback('Encounter added successfully')
            self.show_calendar(self.week_index)
            self.show_encounters()
            self.selected_calendar()
        except Exception as e:
            self.log_error(f"Error adding encounter: {e}")


    def get_datetime_from_cell(self,week_index, row, column):
        try:
            today = date.today()
            days_to_saturday = (today.weekday() - 5) % 7
            start_date = today - timedelta(days=days_to_saturday) + timedelta(weeks=week_index)
            day = start_date + timedelta(days=column - 1)
            time_slot_start, _ = conf.generate_time_slot(9, 0, 20, 21)[row]
            return dt.datetime.combine(day, time_slot_start)
        
        except Exception as e:
            self.log_error(f"Error in get_datetime_from_cell: {e}")


    def action_modify_patient(self):
        try:
            cursor = self.patient_widget.cursor_coordinate
            # patient_id = self.patient_widget.get_cell_at(Coordinate(cursor.row, 0))
            inputs = ['fname', 'lname', 'dob', 'phone']
            self.query_one('#fname').focus()

            if self.modify_pt == False:

                for i, inp in enumerate(inputs):
                    self.query_one(f'#{inp}').value = self.patient_widget.get_cell_at(Coordinate(cursor.row, i+1))
                    self.query_one(f'#{inp}').styles.background = 'teal'
                    if i==4:
                        self.query_one(f'#{inp}').value = int(self.patient_widget.get_cell_at(Coordinate(cursor.row, i+1)))
                self.modify_pt = True
                pass

            else :
                for i, inp in enumerate(inputs):
                    self.query_one(f'#{inp}').value = ''
                    self.query_one(f'#{inp}').styles.background = self.styles.background
                self.modify_pt = False
        except Exception as e:
            self.log_error(f"Error in modify_patient: {e}")
            


    def add_patient(self, first_name, last_name, phone, date_of_birth):
        if self.modify_pt == False:
            try:
                patient = conf.Patient(first_name=first_name, last_name=last_name, phone=phone, date_of_birth=date_of_birth)
                patient_id = conf.save_to_db(patient)
                self.log_feedback("Patient added successfully.")
                self.show_patients()
                self.calendar_widget.move_cursor(row=0, column=0)
                row_index = self.row_index_id.get(str(patient_id))
                self.patient_widget.move_cursor(row=row_index)
                foldername = f"Z:\\patients\\{patient_id} {patient.first_name} {patient.last_name}"
                isExist = os.path.exists(f'Z:\\patients\\{foldername}')
                self.show_encounters()
                if not isExist:
                    os.makedirs(foldername)

            except Exception as e:
                self.log_error(f"Error adding patient: {e}")


    def update_patient(self, patient_id, first_name, last_name, phone, date_of_birth):
        try:
            self.action_modify_patient()
            old_patient = conf.select_patient_by_id(patient_id)
            conf.update_patient(patient_id=patient_id, first_name=first_name, last_name=last_name, phone=phone, date_of_birth=date_of_birth)
            self.log_feedback("Patient updated successfully.")
            self.show_patients()
            row_index = self.row_index_id.get(str(patient_id))
            self.patient_widget.move_cursor(row=row_index)

            old_foldername = f"Z:\\patients\\{patient_id} {old_patient.first_name} {old_patient.last_name}"
            new_foldername = f"Z:\\patients\\{patient_id} {first_name} {last_name}"
            isExist = os.path.exists(f'Z:\\patients\\{old_foldername}')
            if isExist:
                os.rename(old_foldername, new_foldername)
            else:
                os.makedirs(new_foldername)

        except Exception as e:
            self.log_error(f"Error updating patient: {e}")


    def log_error(self, msg):
        timestamp = dt.datetime.now()
        self.query_one('#feedback').write(f'{timestamp}---[bold red]{str(msg)}')

    def action_next_week(self):
        self.week_index += 1 
        self.show_calendar(self.week_index)

    def action_previous_week(self):
        self.week_index -= 1 
        self.show_calendar(self.week_index)

    def log_feedback(self, msg):
        timestamp = dt.datetime.now()
        self.query_one('#feedback').write(f'{timestamp}---[bold #11696b]{str(msg)}')


    def show_patients(self):
        try:
            current_row = self.patient_widget.cursor_row
            current_column = self.patient_widget.cursor_column
            self.patient_widget.clear()
            patients = iter(conf.select_all_starts_with())

            self.row_index_id = {}
            if patients is not None:
                for index, patient in enumerate(patients):
                    patient_id = patient[0]
                    self.patient_widget.add_row(*patient, key=patient_id)
                    self.row_index_id.update({patient_id: index})
                    # self.log_feedback()
                self.patient_widget.move_cursor(row=current_row, column=current_column)
        except Exception as e:
            self.log_error("Error occurred in show_patients: " + str(e))


    def show_encounters(self):
        try:
            if self.patient_widget.row_count == 0:
                return

            self.encounter_widget.clear()
            pt_id = int(self.patient_widget.get_row_at(self.patient_widget.cursor_row)[0])
            # self.log_feedback(pt_id)
            encounters = iter(conf.select_all_pt_encounters(pt_id))
            for index, row in enumerate(encounters):
                encounter_id = row[0]
                self.encounter_widget.add_row(*row, height=int(len(row[2]) / 20 + 1))
                self.row_index_enc_id.update({encounter_id: index})
        except Exception as e:
            self.log_error("Error occurred in show_encounters: " + str(e))


    def show_calendar(self, week_index):
        try:
            current_row = self.calendar_widget.cursor_row
            current_column = self.calendar_widget.cursor_column

            self.calendar_widget.clear(columns=True)
            schedule = iter(conf.generate_schedule(week_index))
            table = self.query_one('#cal_table')

            # Retrieve the column names from the schedule iterator
            column_names = next(schedule)

                    # Get today's date in the format you've described
            today_str = dt.datetime.today().strftime("%d %b %y")
            today_str = today_str.lstrip("0")

            # Iterate over the column names and add them to the table
            for i, column_name in enumerate(column_names):
                if i == 0:
                    table.add_column(column_name, width=5)
                else:
                    # Check if the column name is today and apply special styling if so
                    if column_name.split(" ", 1)[1] == today_str:
                        table.add_column(Text(column_name, style='bold #FFAA1D'), width=18)  # Modify as needed for your GUI library
                    else:
                        table.add_column(column_name, width=18)

            for row in schedule:
                table.add_row(*row, height=2)

            self.calendar_widget.move_cursor(row=current_row, column=current_column, animate=True)
            self.selected_calendar()
        except Exception as e:
            self.log_error("Error occurred in show_calendar: " + str(e))



    def on_data_table_cell_selected(self, message: DataTable.CellSelected):
        try:
            if message.control.id == 'enc_table':
                self.query_one('#notes').focus()
                self.query_one('#notes').value = self.encounter_widget.get_cell_at(self.encounter_widget.cursor_coordinate)
            if message.control.id == 'cal_table':
                self.selected_calendar()
                self.selected_calendar()
                # self.update_tooltip()
        except Exception as e:
            self.log_error(e)


    # def on_data_table_cell_highlighted(self, message: DataTable.CellHighlighted):
    #     if message.control.id == 'cal_table':
    #         self.update_tooltip()

        
    def selected_calendar(self):
        try:
            cursor = self.calendar_widget.cursor_coordinate
            cursor_value = self.calendar_widget.get_cell_at(cursor)
            if '_' in cursor_value or ':' in cursor_value:
            #     # self.show_patients()
            #     # self.encounter_widget.clear()
                return
        
            # start = tm.time()
            encounter_time = self.get_datetime_from_cell(self.week_index, cursor.row, cursor.column)
            encounter = conf.select_encounter_by_rdv(encounter_time)
            patient_id = encounter.patient_id
            encounter_id = encounter.encounter_id

            row_index = self.row_index_id.get(str(patient_id))
            row_index_enc = self.row_index_enc_id.get(str(encounter_id))
            self.patient_widget.move_cursor(row=row_index, animate=True)
            self.show_encounters()

            # start = tm.time()
            cursor_enc = self.encounter_widget.cursor_coordinate
            self.encounter_widget.cursor_type = 'row'
            self.encounter_widget.move_cursor(row=row_index_enc, column=cursor_enc.column)
            end = tm.time()

            # self.log_feedback(end-start)

        except Exception as e:
            self.log_error(e)


    def on_data_table_row_selected(self, message: DataTable.RowSelected):
        try:
            if message.control.id == 'pt_table':
                if self.modify_pt == True:
                    self.action_modify_patient()
                self.encounter_widget.cursor_type = 'row'
                cursor = self.calendar_widget.cursor_coordinate
                cursor_value = self.calendar_widget.get_cell_at(cursor)
                if '_' not in cursor_value:
                    self.calendar_widget.move_cursor(row=0, column=0)
                self.show_encounters()
            elif message.control.id == 'enc_table':
                self.encounter_widget.cursor_type = 'cell'
                self.calendar_widget.move_cursor(row=0, column=0)
                self.encounter_widget.cursor_type = 'cell'
                
                self.query_one('#notes').value = self.encounter_widget.get_cell_at(self.encounter_widget.cursor_coordinate)
                self.query_one('#notes').focus()
        except Exception as e:
            self.log_error(e)
            

    
# ------------------------------------------------------------------------Main App-----------------------------------------------------------------------------------------
class PMSApp(App):
    BINDINGS = [("ctrl+left", "previous_week", "Previous Week"),
            ("ctrl+right", "next_week", "Next Week"),
            ("f1", "add_encounter", "Add Encounter"),
            ("f2", "modify_patient", "Modify Patient"),
            ("ctrl+delete", "delete_encounter", "Delete Encounter"),
            ("f5", "clear_inputs", "Clear"),
            ("f10", "request_export", "Export")]
    
    CSS_PATH = 'styling.css'
    TITLE = 'TerminalPMS'
    SUB_TITLE = 'by Dr.Abdennebi Tarek'
    SCREENS = {"calendar": Calendar()}

    def on_mount(self):
        self.push_screen(self.SCREENS.get('calendar'))

    def action_request_export(self) -> None:
        self.push_screen(PrintExportScreen())

if __name__ == "__main__":
    app = PMSApp()
    app.run()

 