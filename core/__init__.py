from exporters.csv_exporter import CSVExporter

from .crawler import crawl_site
from .parser import parse_course_page


def write_csv(records, output_path):
    exporter = CSVExporter()
    exporter.export(records, output_path)

__all__ = ['crawl_site', 'parse_course_page', 'write_csv']
