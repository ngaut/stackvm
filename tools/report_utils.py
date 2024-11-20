import os
from flask import url_for
from datetime import datetime
import logging

from app.instructions.tools import tool
from app.config.settings import GENERATED_FILES_DIR

logger = logging.getLogger(__name__)

def generate_file_download_link(content: str):
    """
    Generates a download link for the given content. It usually used to generate a report for download.

    Arguments:
    - `content`: The content to be downloaded.

    Output: The download link for the content (report or other format).

    Best practice:
    - Append download link to the final answer, the final answer format should be like:
    ```
    <originalfinal answer>
    [Download](<download link>)
    ```
    """
    try:
        # Generate a unique filename
        filename = f"generated_{datetime.now().strftime('%Y%m%d%H%M%S')}.md"
        file_path = os.path.join(GENERATED_FILES_DIR, filename)

        # Write the markdown content to a file
        with open(file_path, "w") as file:
            file.write(content)

        # Get STACKVM_HOST from environment variables
        stackvm_host = os.getenv('STACKVM_HOST')

        if stackvm_host:
            # Ensure the host does not have a trailing slash
            stackvm_host = stackvm_host.rstrip('/')
            download_link = f"{stackvm_host}/api/download/{filename}"
        else:
            raise ValueError("STACKVM_HOST is not set in environment variables.")

        return download_link
    except Exception as e:
        logger.error(f"Error generating file for download: {str(e)}", exc_info=True)
        raise ValueError(f"Error generating file for download: {str(e)}")