#! /bin/sh

set -e

# detech linux or macos
if [ "$(uname)" = "Darwin" ]; then
    # macos -> /Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Comp/
    
    echo "Installing OpenCaptions for DaVinci Resolve on macOS..."
    
    rm /Library/Application\ Support/Blackmagic\ Design/DaVinci\ Resolve/Fusion/Scripts/Comp/OpenCaptions*.py
    cp OpenCaptionsAuto.py /Library/Application\ Support/Blackmagic\ Design/DaVinci\ Resolve/Fusion/Scripts/Comp/
    cp OpenCaptionsStudio.py /Library/Application\ Support/Blackmagic\ Design/DaVinci\ Resolve/Fusion/Scripts/Comp/
    cp OpenCaptionsFix.py /Library/Application\ Support/Blackmagic\ Design/DaVinci\ Resolve/Fusion/Scripts/Comp/

else
    echo "Unsupported OS: $(uname)"
    exit 1
fi

echo "done"