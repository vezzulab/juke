"""What the bundled app runs."""

import sys

if len(sys.argv) > 1 and sys.argv[1] == "--youtube-helper":       # yt-dlp runs in its own short-lived process
    from juke.api.youtube_helper import main as helper

    sys.exit(helper(sys.argv[2:]))

from juke.main import main

sys.exit(main())
