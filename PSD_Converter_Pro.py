import tkinter as tk
from tkinter import filedialog, Listbox, Checkbutton, IntVar, StringVar, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageTk
from psd_tools import PSDImage
from psd_tools.constants import Resource
import os
import zipfile
import threading
import time
import json
import subprocess

CONFIG_FILE = os.path.expanduser("~/.psd_converter_config.json")

def load_config():
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except Exception:
        pass

def fixed_point_to_float(value):
    return value / 65536

def get_psd_dpi(file_path):
    psd = PSDImage.open(file_path)
    res_key = Resource.RESOLUTION_INFO.value if hasattr(Resource.RESOLUTION_INFO, 'value') else 1005
    if res_key in psd.image_resources:
        resource = psd.image_resources[res_key]
        data = getattr(resource, 'data', None)
        if data:
            dpi_x = fixed_point_to_float(data.horizontal)
            dpi_y = fixed_point_to_float(data.vertical)
            if data.horizontal_unit == 1 and data.vertical_unit == 1:
                return dpi_x, dpi_y
            else:
                return None
    return None

class PSDConverterApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("PSD to JPG and PDF Converter")
        self.geometry("900x700")
        self.resizable(False, False)
        self.file_list = []
        self.stop_flag = False

        config = load_config()

        self.jpg_subfolder = StringVar(value="jpg")
        self.pdf_filename = StringVar(value="pdf")
        self.jpg_quality = IntVar(value=100)
        self.pdf_quality = IntVar(value=config.get("pdf_quality", 85))
        self.create_zip = IntVar(value=0)

        self._setup_ui()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        save_config({"pdf_quality": self.pdf_quality.get()})
        self.destroy()

    def _setup_ui(self):
        tk.Button(self, text="Select PSD or JPG Files", command=self.select_files).place(x=10, y=10, width=180)
        tk.Button(self, text="Select Folder", command=self.select_folder).place(x=200, y=10, width=130)

        self.listbox = Listbox(self, selectmode=tk.MULTIPLE)
        self.listbox.place(x=10, y=50, width=500, height=350)
        self.listbox.drop_target_register(DND_FILES)
        self.listbox.dnd_bind('<<Drop>>', self.drop_files)
        self.listbox.bind('<Double-Button-1>', self.import_files_on_double_click)

        self.preview_label = tk.Label(self, text="No preview available", relief=tk.SUNKEN)
        self.preview_label.place(x=520, y=50, width=350, height=350)

        tk.Button(self, text="Clear All", command=self.clear_all).place(x=10, y=410)
        tk.Button(self, text="Select All", command=self.select_all).place(x=100, y=410)
        tk.Button(self, text="Deselect All", command=self.deselect_all).place(x=210, y=410)

        tk.Label(self, text="JPG Output Subfolder:").place(x=10, y=450)
        tk.Entry(self, textvariable=self.jpg_subfolder).place(x=150, y=450, width=100)
        tk.Label(self, text="PDF Filename:").place(x=10, y=480)
        tk.Entry(self, textvariable=self.pdf_filename).place(x=150, y=480, width=100)

        tk.Label(self, text="JPEG Quality (%):").place(x=10, y=510)
        tk.Scale(self, from_=1, to=100, orient='horizontal', variable=self.jpg_quality).place(x=150, y=500, width=150)

        tk.Label(self, text="PDF Image Quality (%):").place(x=320, y=510)
        tk.Scale(self, from_=10, to=100, orient='horizontal', variable=self.pdf_quality).place(x=470, y=500, width=150)

        Checkbutton(self, text="Create ZIP of converted JPGs", variable=self.create_zip).place(x=10, y=560)

        tk.Button(self, text="Convert to JPG", command=self.convert_to_jpg).place(x=10, y=600, width=120)
        tk.Button(self, text="Create PDF", command=self.create_pdf).place(x=150, y=600, width=120)
        # Changed button text here as requested
        tk.Button(self, text="Convert JPGs and Create PDF", command=self.convert_psds_and_create_pdf).place(x=300, y=600, width=210)
        tk.Button(self, text="Stop Process", command=self.stop_process).place(x=540, y=600, width=120)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self, variable=self.progress_var, maximum=100)
        self.progress_bar.place(x=10, y=640, width=700, height=20)

        self.status_label = tk.Label(self, text="Idle", anchor="w")
        self.status_label.place(x=10, y=670, width=700, height=20)

        tk.Label(self, text="Developed by Kaparthi Sagar", fg="gray").place(x=650, y=680)

        self.listbox.bind("<<ListboxSelect>>", self.preview_image)

    def import_files_on_double_click(self, event):
        files = filedialog.askopenfilenames(filetypes=[("PSD Files","*.psd"), ("JPEG Files","*.jpg;*.jpeg")])
        for f in files:
            if f not in self.file_list:
                self.file_list.append(f)
                self.listbox.insert(tk.END, os.path.basename(f))

    def select_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Image Files", "*.psd *.jpg *.jpeg")])
        for f in files:
            if f not in self.file_list:
                self.file_list.append(f)
                self.listbox.insert(tk.END, os.path.basename(f))

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            for file in os.listdir(folder):
                if file.lower().endswith(('.psd', '.jpg', '.jpeg')):
                    fpath = os.path.join(folder, file)
                    if fpath not in self.file_list:
                        self.file_list.append(fpath)
                        self.listbox.insert(tk.END, os.path.basename(fpath))

    def drop_files(self, event):
        files = self.tk.splitlist(event.data)
        for f in files:
            if os.path.isfile(f) and f.lower().endswith(('.psd', '.jpg', '.jpeg')):
                if f not in self.file_list:
                    self.file_list.append(f)
                    self.listbox.insert(tk.END, os.path.basename(f))
            elif os.path.isdir(f):
                for file in os.listdir(f):
                    if file.lower().endswith(('.psd', '.jpg', '.jpeg')):
                        fpath = os.path.join(f, file)
                        if fpath not in self.file_list:
                            self.file_list.append(fpath)
                            self.listbox.insert(tk.END, os.path.basename(fpath))

    def clear_all(self):
        self.file_list.clear()
        self.listbox.delete(0, tk.END)
        self.preview_label.config(image="", text="No preview available")
        self.status_label.config(text="Idle")
        self.progress_var.set(0)

    def select_all(self):
        self.listbox.select_set(0, tk.END)

    def deselect_all(self):
        self.listbox.select_clear(0, tk.END)

    def preview_image(self, event):
        try:
            idxs = self.listbox.curselection()
            if idxs:
                path = self.file_list[idxs[0]]
                if path.lower().endswith(".psd"):
                    psd = PSDImage.open(path)
                    img = psd.composite()
                else:
                    img = Image.open(path)
                img.thumbnail((350, 350))
                self._tk_img = ImageTk.PhotoImage(img)
                self.preview_label.config(image=self._tk_img, text="")
            else:
                self.preview_label.config(image="", text="No preview available")
        except Exception:
            self.preview_label.config(image="", text="No preview available")

    def stop_process(self):
        self.stop_flag = True
        self.status_label.config(text="Stopping...")

    def convert_to_jpg(self):
        threading.Thread(target=self._convert_to_jpg).start()

    def _convert_to_jpg(self):
        self.stop_flag = False
        start_time = time.time()
        self.status_label.config(text="Starting JPG conversion...")
        dest_folder = os.path.join(os.path.dirname(self.file_list[0]) if self.file_list else os.getcwd(), self.jpg_subfolder.get())
        os.makedirs(dest_folder, exist_ok=True)
        quality = self.jpg_quality.get()
        converted = []
        total_files = len(self.file_list)
        first_successful_dpi = None  # Track DPI from any successful file
        last_known_dpi = None

        for idx, fpath in enumerate(self.file_list):
            if self.stop_flag:
                self.status_label.config(text="Conversion stopped.")
                self.progress_var.set(0)
                return
            try:
                base = os.path.basename(fpath)
                name, _ = os.path.splitext(base)
                dpi = None
                img = None

                if fpath.lower().endswith(".psd"):
                    try:
                        dpi = get_psd_dpi(fpath)
                        psd = PSDImage.open(fpath)
                        img = psd.composite()
                        if dpi is not None:
                            if first_successful_dpi is None:
                                first_successful_dpi = dpi
                            last_known_dpi = dpi
                    except Exception as e:
                        print(f"psd-tools failed for {fpath} with error: {e}. Trying fallback.")
                        try:
                            img = Image.open(fpath)
                            dpi = img.info.get('dpi', None)
                            img.load()
                            if img.mode != 'RGB':
                                img = img.convert('RGB')
                            if dpi is not None:
                                if first_successful_dpi is None:
                                    first_successful_dpi = dpi
                                last_known_dpi = dpi
                        except Exception as e2:
                            print(f"PIL fallback failed for {fpath} with error: {e2}. Trying ImageMagick fallback.")
                            out_path = os.path.join(dest_folder, f"{name}.jpg")
                            convert_installed = subprocess.call(["convert", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
                            dpi = last_known_dpi if last_known_dpi is not None else first_successful_dpi
                            if convert_installed:
                                cmd = ["convert", fpath, "-quality", str(quality)]
                                if dpi:
                                    cmd.extend(["-density", str(int(dpi[0]))])
                                cmd.append(out_path)
                                subprocess.run(cmd, check=True)
                                converted.append(out_path)
                                progress = ((idx + 1) / total_files) * 100
                                self.progress_var.set(progress)
                                self.status_label.config(text=f"Converted {idx + 1}/{total_files}: {name} via ImageMagick")
                                self.update_idletasks()
                                continue
                            else:
                                raise RuntimeError(f"No conversion method available for {fpath}. Install Pillow-PSD or ImageMagick.")
                else:
                    img = Image.open(fpath)
                    dpi = img.info.get('dpi', None)
                    if dpi is not None:
                        if first_successful_dpi is None:
                            first_successful_dpi = dpi
                        last_known_dpi = dpi

                if img is None:
                    raise RuntimeError(f"Failed to load image for {fpath}")

                out_path = os.path.join(dest_folder, f"{name}.jpg")
                if dpi is None:
                    dpi = last_known_dpi if last_known_dpi is not None else first_successful_dpi
                if dpi is not None:
                    img.convert("RGB").save(out_path, "JPEG", quality=quality, dpi=dpi)
                else:
                    img.convert("RGB").save(out_path, "JPEG", quality=quality)

                converted.append(out_path)
                progress = ((idx + 1) / total_files) * 100
                self.progress_var.set(progress)
                self.status_label.config(text=f"Converting to JPG: {idx + 1}/{total_files}")
                self.update_idletasks()

            except Exception as ex:
                print(f"Error converting {fpath}: {ex}")
                continue

        if self.create_zip.get() and converted:
            self.status_label.config(text="Creating ZIP archive...")
            zip_path = os.path.join(dest_folder, "converted_jpgs.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                for jpg in converted:
                    zf.write(jpg, os.path.basename(jpg))
            self.update_idletasks()

        elapsed = time.time() - start_time
        self.status_label.config(text=f"JPG Conversion completed in {elapsed:.2f} seconds")
        self.progress_var.set(100)

    def create_pdf(self):
        threading.Thread(target=self._create_pdf).start()

    def _create_pdf(self):
        self.stop_flag = False
        start_time = time.time()
        self.status_label.config(text="Starting PDF creation...")
        pdf_imgs = []
        total_files = len(self.file_list)
        pdf_quality = self.pdf_quality.get()
        for idx, fpath in enumerate(self.file_list):
            if self.stop_flag:
                self.status_label.config(text="PDF creation stopped.")
                self.progress_var.set(0)
                return
            try:
                if fpath.lower().endswith(".psd"):
                    psd = PSDImage.open(fpath)
                    img = psd.composite()
                else:
                    img = Image.open(fpath)
                img = img.convert("RGB")
                img_bytes_path = f"_temp_pdf_img_{idx}.jpg"
                img.save(img_bytes_path, "JPEG", quality=pdf_quality)
                img_for_pdf = Image.open(img_bytes_path)
                pdf_imgs.append(img_for_pdf)
            except Exception as e:
                print(f"Error creating PDF image from {fpath}: {e}")
                continue
            progress = ((idx + 1) / total_files) * 100
            self.progress_var.set(progress)
            self.status_label.config(text=f"Adding images to PDF: {idx + 1}/{total_files}")
            self.update_idletasks()

        if pdf_imgs:
            jpg_folder = os.path.join(os.path.dirname(
                self.file_list[0]) if self.file_list else os.getcwd(), self.jpg_subfolder.get())
            os.makedirs(jpg_folder, exist_ok=True)
            pdf_path = os.path.join(jpg_folder, self.pdf_filename.get() + ".pdf")
            pdf_imgs[0].save(pdf_path, save_all=True,
                            append_images=pdf_imgs[1:], resolution=100.0)
            for idx in range(len(pdf_imgs)):
                try:
                    os.remove(f"_temp_pdf_img_{idx}.jpg")
                except Exception:
                    pass
            elapsed = time.time() - start_time
            self.status_label.config(
                text=f"PDF created in {elapsed:.2f} seconds: {pdf_path}")
            self.progress_var.set(100)

    def convert_psds_and_create_pdf(self):
        threading.Thread(target=self._convert_psds_and_create_pdf).start()

    def _convert_psds_and_create_pdf(self):
        self.stop_flag = False
        start_time = time.time()
        self.status_label.config(text="Starting PSD to JPG conversion and PDF creation...")

        dest_folder = os.path.join(os.path.dirname(
            self.file_list[0]) if self.file_list else os.getcwd(), self.jpg_subfolder.get())
        os.makedirs(dest_folder, exist_ok=True)
        quality = self.jpg_quality.get()
        pdf_quality = self.pdf_quality.get()
        converted = []
        total_files = len(self.file_list)
        first_successful_dpi = None
        last_known_dpi = None

        for idx, fpath in enumerate(self.file_list):
            if self.stop_flag:
                self.status_label.config(text="Conversion stopped.")
                self.progress_var.set(0)
                return
            try:
                base = os.path.basename(fpath)
                name, _ = os.path.splitext(base)
                dpi = None
                img = None

                if fpath.lower().endswith(".psd"):
                    try:
                        dpi = get_psd_dpi(fpath)
                        psd = PSDImage.open(fpath)
                        img = psd.composite()
                        if dpi is not None:
                            if first_successful_dpi is None:
                                first_successful_dpi = dpi
                            last_known_dpi = dpi
                    except Exception as e:
                        print(f"psd-tools failed for {fpath} with error: {e}. Trying fallback.")
                        try:
                            img = Image.open(fpath)
                            dpi = img.info.get('dpi', None)
                            img.load()
                            if img.mode != 'RGB':
                                img = img.convert('RGB')
                            if dpi is not None:
                                if first_successful_dpi is None:
                                    first_successful_dpi = dpi
                                last_known_dpi = dpi
                        except Exception as e2:
                            print(f"PIL fallback failed for {fpath} with error: {e2}. Trying ImageMagick fallback.")
                            out_path = os.path.join(dest_folder, f"{name}.jpg")
                            convert_installed = subprocess.call(
                                ["convert", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
                            dpi = last_known_dpi if last_known_dpi is not None else first_successful_dpi
                            if convert_installed:
                                cmd = ["convert", fpath, "-quality", str(quality)]
                                if dpi:
                                    cmd.extend(["-density", str(int(dpi[0]))])
                                cmd.append(out_path)
                                subprocess.run(cmd, check=True)
                                converted.append(out_path)
                                progress = ((idx + 1) / total_files) * 50
                                self.progress_var.set(progress)
                                self.status_label.config(
                                    text=f"Converted {idx + 1}/{total_files}: {name} via ImageMagick")
                                self.update_idletasks()
                                continue
                            else:
                                raise RuntimeError(
                                    f"No conversion method available for {fpath}. Install Pillow-PSD or ImageMagick.")
                else:
                    img = Image.open(fpath)
                    dpi = img.info.get('dpi', None)
                    if dpi is not None:
                        if first_successful_dpi is None:
                            first_successful_dpi = dpi
                        last_known_dpi = dpi

                if img is None:
                    raise RuntimeError(f"Failed to load image for {fpath}")

                out_path = os.path.join(dest_folder, f"{name}.jpg")
                if dpi is None:
                    dpi = last_known_dpi if last_known_dpi is not None else first_successful_dpi
                if dpi is not None:
                    img.convert("RGB").save(
                        out_path, "JPEG", quality=quality, dpi=dpi)
                else:
                    img.convert("RGB").save(out_path, "JPEG", quality=quality)

                converted.append(out_path)
                progress = ((idx + 1) / total_files) * 50
                self.progress_var.set(progress)
                self.status_label.config(
                    text=f"Converting to JPG: {idx + 1}/{total_files}")
                self.update_idletasks()

            except Exception as ex:
                print(f"Error converting {fpath}: {ex}")
                continue

        pdf_imgs = []
        for idx, jpg in enumerate(converted):
            try:
                img = Image.open(jpg)
                img = img.convert("RGB")
                img_bytes_path = f"_temp_pdf_img_{idx}.jpg"
                img.save(img_bytes_path, "JPEG", quality=pdf_quality)
                img_for_pdf = Image.open(img_bytes_path)
                pdf_imgs.append(img_for_pdf)
            except Exception as e:
                print(f"Error adding image {jpg} to PDF: {e}")
                continue

            progress = 50 + ((idx + 1) / len(converted)) * 50
            self.progress_var.set(progress)
            self.status_label.config(text=f"Adding images to PDF: {idx + 1}/{len(converted)}")
            self.update_idletasks()

        if pdf_imgs:
            pdf_path = os.path.join(dest_folder, self.pdf_filename.get() + ".pdf")
            pdf_imgs[0].save(pdf_path, save_all=True, append_images=pdf_imgs[1:], resolution=100.0)
            for idx in range(len(pdf_imgs)):
                try:
                    os.remove(f"_temp_pdf_img_{idx}.jpg")
                except Exception:
                    pass

            elapsed = time.time() - start_time
            self.status_label.config(text=f"Conversion and PDF creation completed in {elapsed:.2f} seconds")
            self.progress_var.set(100)

if __name__ == "__main__":
    app = PSDConverterApp()
    app.mainloop()
