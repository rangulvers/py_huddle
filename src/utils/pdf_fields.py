from pdfrw import PdfReader
from loguru import logger

def print_pdf_fields(pdf_path: str):
    """Print all form field names from a PDF."""
    try:
        # Read the PDF
        pdf = PdfReader(pdf_path)
        logger.info(f"Reading PDF: {pdf_path}")
        
        # Store all found fields
        fields = []
        
        # Iterate through pages
        for page_num, page in enumerate(pdf.pages, 1):
            logger.info(f"Checking page {page_num}")
            
            if page.Annots:
                for annotation in page.Annots:
                    if annotation.T:
                        field_name = str(annotation.T)
                        field_type = str(annotation.FT) if hasattr(annotation, 'FT') else 'Unknown'
                        fields.append((field_name, field_type))
                        logger.debug(f"Found field: {field_name} (Type: {field_type})")

        # Print results in a formatted way
        if fields:
            logger.info("\nFound form fields:")
            print("\nField Name | Type")
            print("-" * 50)
            for field_name, field_type in sorted(fields):
                print(f"{field_name} | {field_type}")
            print(f"\nTotal fields found: {len(fields)}")
        else:
            logger.warning("No form fields found in the PDF")

    except Exception as e:
        logger.error(f"Error reading PDF: {e}")

if __name__ == "__main__":
    # Replace with your template path
    template_path = "templates/01_fahrtkostenzuschsseeinzelblatt neu_V2beschreibbar.pdf"
    print_pdf_fields(template_path)