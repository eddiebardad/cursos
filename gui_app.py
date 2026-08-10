import io
import logging
import sys
import threading
import queue
from contextlib import redirect_stdout, redirect_stderr
from tkinter import filedialog, messagebox

import customtkinter as ctk
from providers import ProviderBase

from cli import _execute_scrape


class QueueWriter(io.TextIOBase):
    def __init__(self, output_queue: queue.Queue):
        self.output_queue = output_queue

    def write(self, text: str):
        if text:
            self.output_queue.put(text)
        return len(text)

    def flush(self):
        pass


class QueueLogHandler(logging.Handler):
    def __init__(self, output_queue: queue.Queue):
        super().__init__()
        self.output_queue = output_queue
        self.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    def emit(self, record: logging.LogRecord):
        try:
            message = self.format(record)
            self.output_queue.put(message + "\n")
        except Exception:
            self.handleError(record)


class ScraperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("Course Scraper")
        self.geometry("880x700")
        self.minsize(780, 620)

        self.output_queue: queue.Queue = queue.SimpleQueue()
        self._build_ui()
        self._refresh_output()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)

        header_frame = ctk.CTkFrame(self, corner_radius=12, fg_color="#2b2b2b")
        header_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        header_label = ctk.CTkLabel(
            header_frame,
            text="Course Scraper",
            font=ctk.CTkFont(size=24, weight="bold"),
            anchor="w",
        )
        header_label.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="w")

        description_label = ctk.CTkLabel(
            header_frame,
            text="Enter a starting URL, optional provider override, and generate course data to CSV or JSON-LD.",
            anchor="w",
            wraplength=760,
            justify="left",
        )
        description_label.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="w")

        form_frame = ctk.CTkFrame(self, corner_radius=12)
        form_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        form_frame.grid_columnconfigure(1, weight=1)

        url_label = ctk.CTkLabel(form_frame, text="Starting URL:")
        url_label.grid(row=0, column=0, padx=16, pady=12, sticky="w")
        self.url_entry = ctk.CTkEntry(form_frame, placeholder_text="https://example.com/courses")
        self.url_entry.grid(row=0, column=1, padx=16, pady=12, sticky="ew")

        provider_label = ctk.CTkLabel(form_frame, text="Provider:")
        provider_label.grid(row=1, column=0, padx=16, pady=12, sticky="w")
        provider_values = ["Auto-detect"] + [cls.provider_name for cls in ProviderBase._registry]
        self.provider_menu = ctk.CTkOptionMenu(form_frame, values=provider_values, width=200)
        self.provider_menu.set(provider_values[0])
        self.provider_menu.grid(row=1, column=1, padx=16, pady=12, sticky="ew")

        max_pages_label = ctk.CTkLabel(form_frame, text="Max pages to crawl:")
        max_pages_label.grid(row=2, column=0, padx=16, pady=12, sticky="w")
        self.max_pages_entry = ctk.CTkEntry(form_frame, placeholder_text="100")
        self.max_pages_entry.insert(0, "100")
        self.max_pages_entry.grid(row=2, column=1, padx=16, pady=12, sticky="ew")

        self.render_checkbox = ctk.CTkCheckBox(form_frame, text="Render JavaScript with Playwright")
        self.render_checkbox.grid(row=3, column=0, columnspan=2, padx=16, pady=12, sticky="w")

        output_label = ctk.CTkLabel(form_frame, text="Output file:")
        output_label.grid(row=4, column=0, padx=16, pady=12, sticky="w")
        output_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        output_row.grid(row=4, column=1, padx=16, pady=12, sticky="ew")
        output_row.grid_columnconfigure(0, weight=1)

        self.output_entry = ctk.CTkEntry(output_row, placeholder_text="results.csv")
        self.output_entry.insert(0, "results.csv")
        self.output_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        output_browse = ctk.CTkButton(output_row, text="Browse…", width=100, command=self._browse_output_file)
        output_browse.grid(row=0, column=1, sticky="e")

        button_frame = ctk.CTkFrame(form_frame, corner_radius=12)
        button_frame.grid(row=5, column=0, columnspan=2, padx=16, pady=(10, 16), sticky="ew")
        button_frame.grid_columnconfigure(0, weight=1)

        self.run_button = ctk.CTkButton(button_frame, text="Run Scrape", font=ctk.CTkFont(size=16, weight="bold"), command=self._on_run)
        self.run_button.grid(row=0, column=0, padx=16, pady=16, sticky="ew")

        self.status_label = ctk.CTkLabel(button_frame, text="Ready", anchor="w", fg_color="transparent")
        self.status_label.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="w")

        output_frame = ctk.CTkFrame(self, corner_radius=12)
        output_frame.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="nsew")
        output_frame.grid_rowconfigure(1, weight=1)
        output_frame.grid_columnconfigure(0, weight=1)

        output_title = ctk.CTkLabel(output_frame, text="Console Output:", anchor="w")
        output_title.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        self.output_text = ctk.CTkTextbox(output_frame, wrap="none", state="disabled")
        self.output_text.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")

        clear_button = ctk.CTkButton(output_frame, text="Clear", width=80, command=self._clear_output)
        clear_button.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="e")

    def _browse_output_file(self):
        path = filedialog.asksaveasfilename(
            title="Save output file",
            defaultextension=".csv",
            filetypes=[
                ("CSV files", "*.csv"),
                ("JSON-LD files", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.output_entry.delete(0, ctk.END)
            self.output_entry.insert(0, path)

    def _on_run(self):
        url = self.url_entry.get().strip()
        provider = self.provider_menu.get()
        max_pages_text = self.max_pages_entry.get().strip()
        render = bool(self.render_checkbox.get())
        output_file = self.output_entry.get().strip()

        if not url:
            messagebox.showwarning("Validation error", "Please enter a starting URL.")
            return

        if not max_pages_text.isdigit() or int(max_pages_text) < 1:
            messagebox.showwarning("Validation error", "Max pages must be a positive integer.")
            return

        if not output_file:
            messagebox.showwarning("Validation error", "Please select an output file path.")
            return

        max_pages = int(max_pages_text)
        provider_value = None if provider == "Auto-detect" else provider

        if provider_value is None and "aprende.org" in url:
            provider_value = "Aprende"

        self.run_button.configure(state="disabled")
        self._set_status("Running…")
        self._append_output("Starting scrape...\n")

        worker = threading.Thread(
            target=self._run_scrape,
            args=(url, provider_value, max_pages, render, output_file),
            daemon=True,
        )
        worker.start()

    def _run_scrape(self, url: str, provider: str | None, max_pages: int, render: bool, output_file: str):
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers.copy()
        root_logger.handlers.clear()

        handler = QueueLogHandler(self.output_queue)
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        stdout_writer = QueueWriter(self.output_queue)
        stderr_writer = QueueWriter(self.output_queue)

        try:
            with redirect_stdout(stdout_writer), redirect_stderr(stderr_writer):
                _execute_scrape(url, provider, max_pages, render, output_file)
            self.output_queue.put("Scraping completed successfully.\n")
        except SystemExit as exc:
            self.output_queue.put(f"Scraping finished with exit code {exc.code}.\n")
        except Exception as exc:  # pragma: no cover
            self.output_queue.put(f"Unexpected error: {exc}\n")
        finally:
            root_logger.removeHandler(handler)
            root_logger.handlers.extend(original_handlers)
            self.after(0, self._scrape_complete)

    def _scrape_complete(self):
        self.run_button.configure(state="normal")
        self._set_status("Ready")

    def _refresh_output(self):
        while not self.output_queue.empty():
            message = self.output_queue.get_nowait()
            self.output_text.configure(state="normal")
            self.output_text.insert(ctk.END, message)
            self.output_text.configure(state="disabled")
            self.output_text.see(ctk.END)
        self.after(100, self._refresh_output)

    def _append_output(self, text: str):
        self.output_queue.put(text)

    def _clear_output(self):
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", ctk.END)
        self.output_text.configure(state="disabled")

    def _set_status(self, text: str):
        self.status_label.configure(text=text)


if __name__ == "__main__":
    app = ScraperApp()
    app.mainloop()
