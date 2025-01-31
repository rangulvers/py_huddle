import os
from pdfrw import PdfReader
from loguru import logger
import re

def clean_number(value: str) -> float:
    """
    Clean and convert string value to float, handling parentheses and other characters.
    
    Args:
        value: String value to convert
        
    Returns:
        float: Cleaned number
    """
    try:
        # Remove parentheses and any other non-numeric characters except decimal points
        cleaned = re.sub(r'[^\d.]', '', str(value))
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        raise ValueError(f"Could not convert '{value}' to number")

def sum_kilometers(pdf_directory: str):
    """
    Sum up all 'Summe km' values from PDFs in directory.
    
    Args:
        pdf_directory: Directory containing PDF files
    """
    try:
        # Get all PDF files in directory
        pdf_files = sorted([f for f in os.listdir(pdf_directory) if f.endswith('.pdf')])
        total_files = len(pdf_files)
        
        logger.info(f"Found {total_files} PDF files to process")
        
        total_km = 0
        processed_files = []
        failed_files = []

        # Process each PDF
        for pdf_file in pdf_files:
            filepath = os.path.join(pdf_directory, pdf_file)
            logger.debug(f"Processing {pdf_file}")

            try:
                # Read PDF
                template = PdfReader(filepath)
                found_km = False
                
                # Look for Summe km field
                for page in template.pages:
                    if page.Annots:
                        for annotation in page.Annots:
                            if annotation.T and str(annotation.T) == '(Summe km)':
                                if annotation.V:
                                    try:
                                        raw_value = str(annotation.V)
                                        km_value = clean_number(raw_value)
                                        if km_value > 0:  # Only count positive values
                                            total_km += km_value
                                            found_km = True
                                            logger.debug(f"Found {km_value} km in {pdf_file} (raw value: {raw_value})")
                                            processed_files.append((pdf_file, km_value))
                                        else:
                                            logger.warning(f"Zero or negative value found in {pdf_file}: {raw_value}")
                                            failed_files.append((pdf_file, f"Zero or negative value: {raw_value}"))
                                    except ValueError as e:
                                        logger.warning(f"Could not convert value '{annotation.V}' to number in {pdf_file}")
                                        failed_files.append((pdf_file, f"Invalid value: {annotation.V}"))
                
                if not found_km:
                    logger.warning(f"No valid 'Summe km' value found in {pdf_file}")
                    failed_files.append((pdf_file, "No valid km value found"))

            except Exception as e:
                logger.error(f"Error processing {pdf_file}: {e}")
                failed_files.append((pdf_file, str(e)))
                continue

        # Summary
        logger.info("\nSummary:")
        logger.info(f"Successfully processed: {len(processed_files)} of {total_files} files")
        
        # Show successful files and their values
        logger.info("\nProcessed files:")
        for pdf_file, km in processed_files:
            logger.info(f"- {pdf_file}: {km:.2f} km")
        
        # Show failed files
        if failed_files:
            logger.warning("\nFailed files:")
            for pdf_file, reason in failed_files:
                logger.warning(f"- {pdf_file}: {reason}")

        # Print total with clear separation
        logger.info("\n" + "="*50)
        logger.info(f"TOTAL KILOMETERS: {total_km:.2f} km")
        logger.info(f"TOTAL COST (0.30€/km): {(total_km * 0.30):.2f}€")
        logger.info("="*50)

    except Exception as e:
        logger.error(f"Error processing files: {e}")

# Usage example
if __name__ == "__main__":
    pdf_directory = "output/pdfs"  # Update if your path is different
    sum_kilometers(pdf_directory)