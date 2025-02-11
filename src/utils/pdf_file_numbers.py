import os
from pdfrw import PdfReader, PdfWriter, PdfDict
from loguru import logger

def update_page_numbers(pdf_directory: str):
    """
    Update all PDFs in directory with incrementing page numbers (01, 02, etc.).

    Args:
        pdf_directory: Directory containing PDF files
    """
    try:
        # Get all PDF files in directory
        pdf_files = sorted([f for f in os.listdir(pdf_directory) if f.endswith('.pdf')])
        total_files = len(pdf_files)

        logger.info(f"Found {total_files} PDF files to process")
        successful_updates = []

        # Process each PDF
        for page_num, pdf_file in enumerate(pdf_files, 1):
            filepath = os.path.join(pdf_directory, pdf_file)
            formatted_num = f"{page_num:02d}"  # Format as 01, 02, etc.
            logger.debug(f"Processing {pdf_file} - Page {formatted_num}/{total_files:02d}")

            try:
                # Read PDF
                template = PdfReader(filepath)
                updated = False

                # Update page number
                for page in template.pages:
                    if page.Annots:
                        for annotation in page.Annots:
                            if annotation.T and str(annotation.T) == '(Blatt Nr)':  # Exact field name
                                annotation.update(
                                    PdfDict(
                                        V=formatted_num,
                                        AP=None,
                                        AS=None,
                                        DV=formatted_num
                                    )
                                )
                                updated = True
                                logger.debug(f"Updated page number to {formatted_num}")
                                break

                if updated:
                    # Save updated PDF
                    writer = PdfWriter()
                    writer.write(filepath, template)
                    successful_updates.append(pdf_file)
                    logger.debug(f"Saved updated PDF: {pdf_file}")
                else:
                    logger.warning(f"Could not find 'Blatt Nr' field in {pdf_file}")

            except Exception as e:
                logger.error(f"Error processing {pdf_file}: {e}")
                continue

        # Summary
        logger.info(f"Successfully updated {len(successful_updates)} of {total_files} PDFs")

        # List any files that weren't updated
        failed_files = set(pdf_files) - set(successful_updates)
        if failed_files:
            logger.warning("Files not updated:")
            for failed_file in sorted(failed_files):
                logger.warning(f"- {failed_file}")

            # Offer to retry failed files
            if input("Would you like to retry failed files? (y/n): ").lower() == 'y':
                logger.info(f"Retrying {len(failed_files)} files...")
                retry_files = sorted(list(failed_files))
                update_specific_pdfs(pdf_directory, retry_files)

    except Exception as e:
        logger.error(f"Error updating page numbers: {e}")

def update_specific_pdfs(pdf_directory: str, pdf_files: list):
    """Update specific PDF files with page numbers."""
    try:
        total_files = len(pdf_files)
        for page_num, pdf_file in enumerate(pdf_files, 1):
            filepath = os.path.join(pdf_directory, pdf_file)
            formatted_num = f"{page_num:02d}"

            try:
                template = PdfReader(filepath)
                updated = False

                for page in template.pages:
                    if page.Annots:
                        for annotation in page.Annots:
                            if annotation.T and str(annotation.T) == '(Blatt Nr)':
                                annotation.update(
                                    PdfDict(
                                        V=formatted_num,
                                        AP=None,
                                        AS=None,
                                        DV=formatted_num
                                    )
                                )
                                updated = True

                if updated:
                    writer = PdfWriter()
                    writer.write(filepath, template)
                    logger.info(f"Retry successful for {pdf_file}")
                else:
                    logger.warning(f"Retry failed for {pdf_file} - Field not found")

            except Exception as e:
                logger.error(f"Error in retry for {pdf_file}: {e}")

    except Exception as e:
        logger.error(f"Error in retry process: {e}")

# Usage example
if __name__ == "__main__":
    # Get PDF directory from config or use default
    pdf_directory = "output/pdfs"  # Update this path
    update_page_numbers(pdf_directory)
