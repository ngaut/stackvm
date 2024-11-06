import os
from flask import url_for
from datetime import datetime
import logging

from app.instructions.tools import tool
from app.config.settings import GENERATED_FILES_DIR

logger = logging.getLogger(__name__)

@tool
def generate_file_download_link(content: str):
    """
    Generates a download link for the given content. It usually used to generate a report for download.

    Arguments:
    - `content`: The content to be downloaded.

    Output: The download link for the content (report or other format).
    """
    try:
        # Generate a unique filename
        filename = f"generated_{datetime.now().strftime('%Y%m%d%H%M%S')}.md"
        file_path = os.path.join(GENERATED_FILES_DIR, filename)

        # Write the markdown content to a file
        with open(file_path, "w") as file:
            file.write(content)

        # Generate the full download link
        download_link = url_for("api.download_file", filename=filename, _external=True)
        return download_link
    except Exception as e:
        logger.error(f"Error generating file for download: {str(e)}", exc_info=True)
        return ValueError(f"Error generating file for download: {str(e)}")