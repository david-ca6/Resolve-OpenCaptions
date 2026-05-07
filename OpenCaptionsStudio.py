#!/usr/bin/env python3

import re
import tkinter as tk
from tkinter import ttk

version = "0.01.01"
TEMPLATES_FOLDER_NAME = "Captions Templates"

# ------------------------- resolve api connection -------------------------

try:
    resolve # if we run inside Resolve, we already have the resolve object
except NameError:
    from python_get_resolve import GetResolve
    resolve = GetResolve()

project_manager = resolve.GetProjectManager()
project = project_manager.GetCurrentProject()
timeline = project.GetCurrentTimeline() if project else None

# ------------------------- text functions -------------------------

def remove_punctuationText(text):
    punctuation = [".", ","]
    for mark in punctuation:
        text = text.replace(mark, "")
    return text

def apply_text_transform(text, transform):
    if transform == "All Lowercase":
        return text.lower()
    if transform == "All Uppercase":
        return text.upper()
    if transform == "Uppercase Words":
        return text.title()
    return text

def normalize_caption_text(text):
    text = " ".join((text or "").split())
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    text = re.sub(r"([({\[])\s+", r"\1", text)
    return text

# ------------------------- resolve timeline functions -------------------------

def get_current_timeline():
    global project, timeline
    project = project_manager.GetCurrentProject()
    timeline = project.GetCurrentTimeline() if project else None
    return timeline

def get_timeline_fps(current_timeline):
    return float(current_timeline.GetSetting("timelineFrameRate"))

def timecode_to_frame(timecode, fps):
    timecode = str(timecode).replace(";", ":")
    parts = timecode.split(":")
    if len(parts) < 4:
        return 0
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = int(parts[2])
    frames = int(parts[3])
    return int(round(((hours * 3600) + (minutes * 60) + seconds) * fps + frames))

def frame_to_timecode(frame, fps):
    frame = max(0, int(frame))
    fps_int = int(round(fps))
    total_seconds, frames = divmod(frame, fps_int)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"

def get_timeline_start_frame(current_timeline, fps):
    try:
        return int(current_timeline.GetStartFrame())
    except Exception:
        pass
    try:
        return timecode_to_frame(current_timeline.GetStartTimecode(), fps)
    except Exception:
        return 0

def get_current_timeline_frame(current_timeline):
    fps = get_timeline_fps(current_timeline)
    current_frame = timecode_to_frame(current_timeline.GetCurrentTimecode(), fps)
    start_frame = get_timeline_start_frame(current_timeline, fps)
    if current_frame >= start_frame:
        return current_frame - start_frame
    return current_frame

def get_video_tracks():
    current_timeline = get_current_timeline()
    if not current_timeline:
        return []
    track_count = current_timeline.GetTrackCount("video")
    tracks = []
    for index in range(1, track_count + 1):
        track_name = current_timeline.GetTrackName("video", index) or f"Video {index}"
        tracks.append(f"V{index} - {track_name}")
    return tracks

def get_subtitle_tracks():
    current_timeline = get_current_timeline()
    if not current_timeline:
        return []
    track_count = current_timeline.GetTrackCount("subtitle")
    tracks = []
    for index in range(1, track_count + 1):
        track_name = current_timeline.GetTrackName("subtitle", index) or f"Subtitle {index}"
        tracks.append(f"S{index} - {track_name}")
    return tracks

def get_track_index(track_label):
    if not track_label:
        return None
    prefix = track_label.split(" - ", 1)[0]
    try:
        return int(prefix[1:])
    except Exception:
        return None

def find_templates_folder(media_pool):
    root_folder = media_pool.GetRootFolder()

    def search_folder(folder):
        if folder.GetName() == TEMPLATES_FOLDER_NAME:
            return folder
        for subfolder in folder.GetSubFolderList():
            result = search_folder(subfolder)
            if result:
                return result
        return None

    return search_folder(root_folder)

def is_text_plus_template(clip):
    return clip.GetClipProperty("File Path") == ""

def get_available_templates():
    try:
        media_pool = project.GetMediaPool()
        templates_folder = find_templates_folder(media_pool)
        if not templates_folder:
            return []
        templates = []
        for clip in templates_folder.GetClipList():
            if is_text_plus_template(clip):
                clip_name = clip.GetClipProperty("Clip Name")
                if clip_name and clip_name not in templates:
                    templates.append(clip_name)
        templates.sort()
        return templates
    except Exception as error:
        print(f"Error getting templates: {error}")
        return []

def find_text_plus_template_by_name(media_pool, template_name):
    templates_folder = find_templates_folder(media_pool)
    if not templates_folder:
        return None
    for clip in templates_folder.GetClipList():
        if is_text_plus_template(clip) and clip.GetClipProperty("Clip Name") == template_name:
            return clip
    return None

def list_available_templates(media_pool):
    templates_folder = find_templates_folder(media_pool)
    if not templates_folder:
        print(f"No {TEMPLATES_FOLDER_NAME} folder found in Media Pool.")
        return
    templates = []
    for clip in templates_folder.GetClipList():
        if is_text_plus_template(clip):
            clip_name = clip.GetClipProperty("Clip Name")
            templates.append(f"{clip_name} ({TEMPLATES_FOLDER_NAME})")
    if templates:
        print("Available Text+ templates:")
        for template in templates:
            print(f"  {template}")
    else:
        print(f"No Text+ templates found in {TEMPLATES_FOLDER_NAME}.")

def get_subtitles_in_range(current_timeline, subtitle_track_index, in_frame, out_frame):
    items = current_timeline.GetItemListInTrack("subtitle", subtitle_track_index) or []
    subtitles = []
    for item in items:
        start_frame = int(item.GetStart())
        end_frame = int(item.GetEnd())
        if start_frame < out_frame and end_frame > in_frame:
            text_content = normalize_caption_text(item.GetName())
            if text_content:
                subtitles.append({
                    "start_frame": start_frame,
                    "end_frame": end_frame,
                    "text": text_content,
                })
    subtitles.sort(key=lambda row: row["start_frame"])
    return subtitles

def get_template_duration_multiplier(media_pool, current_timeline, text_clip, video_track_index, record_frame):
    duration_multiplier = 1.0
    try:
        test_duration = 100
        test_clip = {
            "mediaPoolItem": text_clip,
            "startFrame": 0,
            "endFrame": test_duration - 1,
            "trackIndex": video_track_index,
            "recordFrame": record_frame,
        }
        test_items = media_pool.AppendToTimeline([test_clip])
        if test_items and len(test_items) > 0:
            test_item = test_items[0]
            test_duration_real = test_item.GetDuration()
            current_timeline.DeleteClips([test_item], False)
            duration_multiplier = test_duration / test_duration_real if test_duration_real > 0 else 1.0
        print(f"Duration multiplier: {duration_multiplier:.3f}")
    except Exception as error:
        print(f"Warning: could not calculate duration multiplier: {error}")
        duration_multiplier = 1.0
    return duration_multiplier

def create_text_plus_clip(current_timeline, template_name, video_track_index, start_frame, end_frame, text_content):
    if not current_timeline:
        print("No active timeline.")
        return False
    if video_track_index is None:
        print("No destination video track selected.")
        return False
    media_pool = project.GetMediaPool()
    text_clip = find_text_plus_template_by_name(media_pool, template_name)
    if not text_clip:
        print(f"Text+ template {template_name} not found in Media Pool.")
        list_available_templates(media_pool)
        return False
    duration = max(1, int(end_frame) - int(start_frame))
    duration_multiplier = get_template_duration_multiplier(
        media_pool,
        current_timeline,
        text_clip,
        video_track_index,
        max(0, int(start_frame)),
    )
    new_duration = max(1, int(duration * duration_multiplier + 0.999))
    new_clip = {
        "mediaPoolItem": text_clip,
        "startFrame": 0,
        "endFrame": new_duration - 1,
        "trackIndex": video_track_index,
        "recordFrame": int(start_frame),
    }
    timeline_items = media_pool.AppendToTimeline([new_clip])
    if not timeline_items or len(timeline_items) == 0:
        print("Error: failed to create Text+ clip.")
        return False
    timeline_item = timeline_items[0]
    timeline_item.SetClipColor("Green")
    if timeline_item.GetFusionCompCount() == 0:
        print("Warning: created clip has no Fusion composition.")
        return False
    comp = timeline_item.GetFusionCompByIndex(1)
    if not comp:
        print("Warning: no Fusion composition found in Text+ clip.")
        return False
    text_tool = comp.FindToolByID("TextPlus")
    if not text_tool:
        print("Warning: no TextPlus tool found in Text+ clip.")
        return False
    text_tool.SetInput("StyledText", text_content)
    return True

def get_studio_range_payload(current_timeline, template_name, subtitle_track_index, video_track_index, in_frame, out_frame, remove_punctuation=True, text_transform="Keep"):
    if not current_timeline:
        print("No active timeline.")
        return None
    if not template_name:
        print("No Text+ template selected.")
        return None
    if subtitle_track_index is None:
        print("No source subtitle track selected.")
        return None
    if video_track_index is None:
        print("No destination video track selected.")
        return None
    if in_frame is None or out_frame is None:
        print("Set IN and OUT before processing.")
        return None
    if out_frame <= in_frame:
        print("OUT must be after IN.")
        return None
    subtitles = get_subtitles_in_range(current_timeline, subtitle_track_index, in_frame, out_frame)
    if not subtitles:
        print("No subtitles found in selected range.")
        return None
    merged_text = normalize_caption_text(" ".join(row["text"] for row in subtitles))
    if remove_punctuation:
        merged_text = remove_punctuationText(merged_text)
    merged_text = apply_text_transform(merged_text, text_transform)
    return {
        "count": len(subtitles),
        "start_frame": int(in_frame),
        "end_frame": int(out_frame),
        "text": merged_text,
    }

def process_studio_payload(current_timeline, template_name, video_track_index, payload, text_content=None):
    if not payload:
        return 0
    if text_content is None:
        text_content = payload["text"]
    if not text_content.strip():
        print("No text entered.")
        return 0
    start_frame = payload["start_frame"]
    end_frame = payload["end_frame"]
    success = create_text_plus_clip(
        current_timeline,
        template_name,
        video_track_index,
        start_frame,
        end_frame,
        text_content,
    )
    if success:
        print(f"Created merged Text+ clip from {payload['count']} subtitle item(s): {text_content}")
        return payload["count"]
    return 0

def process_studio_range(current_timeline, template_name, subtitle_track_index, video_track_index, in_frame, out_frame, remove_punctuation=True, text_transform="Keep"):
    payload = get_studio_range_payload(
        current_timeline,
        template_name,
        subtitle_track_index,
        video_track_index,
        in_frame,
        out_frame,
        remove_punctuation=remove_punctuation,
        text_transform=text_transform,
    )
    if not payload:
        return 0
    return process_studio_payload(current_timeline, template_name, video_track_index, payload)

# ------------------------- ui -------------------------

def main():
    current_project = project_manager.GetCurrentProject()
    if not current_project:
        print("No active project.")
        return

    selected_settings = {}
    text_transform_options = ["Keep", "Uppercase Words", "All Uppercase", "All Lowercase"]

    setup_root = tk.Tk()
    setup_root.focus_force()
    setup_root.attributes("-topmost", True)
    setup_root.title("OpenCaptions Studio Setup " + version)
    setup_root.geometry("640x400")
    setup_root.minsize(640, 380)

    setup_status_var = tk.StringVar()
    template_var = tk.StringVar()
    source_track_var = tk.StringVar()
    destination_track_var = tk.StringVar()
    remove_punctuation_var = tk.BooleanVar(value=True)
    text_transform_var = tk.StringVar(value=text_transform_options[0])

    templates = get_available_templates()
    subtitle_tracks = get_subtitle_tracks()
    video_tracks = get_video_tracks()
    template_var.set(templates[0] if templates else "")
    source_track_var.set(subtitle_tracks[0] if subtitle_tracks else "")
    destination_track_var.set(video_tracks[0] if video_tracks else "")

    def set_setup_status(message):
        setup_status_var.set(message)
        print(message)

    def refresh_all():
        nonlocal templates, subtitle_tracks, video_tracks
        templates = get_available_templates()
        subtitle_tracks = get_subtitle_tracks()
        video_tracks = get_video_tracks()
        template_combo["values"] = templates
        source_track_combo["values"] = subtitle_tracks
        destination_track_combo["values"] = video_tracks
        if templates and template_var.get() not in templates:
            template_var.set(templates[0])
        elif not templates:
            template_var.set("")
        if subtitle_tracks and source_track_var.get() not in subtitle_tracks:
            source_track_var.set(subtitle_tracks[0])
        elif not subtitle_tracks:
            source_track_var.set("")
        if video_tracks and destination_track_var.get() not in video_tracks:
            destination_track_var.set(video_tracks[0])
        elif not video_tracks:
            destination_track_var.set("")
        set_setup_status(f"Found {len(templates)} template(s), {len(subtitle_tracks)} subtitle track(s), {len(video_tracks)} video track(s).")

    def start_studio():
        selected_settings.update({
            "template_name": template_var.get(),
            "subtitle_track_index": get_track_index(source_track_var.get()),
            "video_track_index": get_track_index(destination_track_var.get()),
            "remove_punctuation": remove_punctuation_var.get(),
            "text_transform": text_transform_var.get(),
        })
        setup_root.destroy()

    setup_content = ttk.Frame(setup_root, padding=24)
    setup_content.grid(row=0, column=0, sticky="nsew")
    setup_root.columnconfigure(0, weight=1)
    setup_root.rowconfigure(0, weight=1)
    setup_content.columnconfigure(0, weight=1)

    setup_section = ttk.LabelFrame(setup_content, text="Tracks", padding=(16, 12))
    setup_section.grid(row=0, column=0, sticky="ew")
    setup_section.columnconfigure(1, weight=1)

    ttk.Label(setup_section, text="Template").grid(row=0, column=0, sticky="w")
    template_combo = ttk.Combobox(setup_section, textvariable=template_var, values=templates, state="readonly")
    template_combo.grid(row=0, column=1, sticky="ew", padx=(12, 0))

    ttk.Label(setup_section, text="Source Sub Track").grid(row=1, column=0, sticky="w", pady=(12, 0))
    source_track_combo = ttk.Combobox(setup_section, textvariable=source_track_var, values=subtitle_tracks, state="readonly")
    source_track_combo.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(12, 0))

    ttk.Label(setup_section, text="Destination Video Track").grid(row=2, column=0, sticky="w", pady=(12, 0))
    destination_track_combo = ttk.Combobox(setup_section, textvariable=destination_track_var, values=video_tracks, state="readonly")
    destination_track_combo.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=(12, 0))

    ttk.Button(setup_section, text="Refresh", command=refresh_all).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(16, 0))

    options_section = ttk.LabelFrame(setup_content, text="Options", padding=(16, 12))
    options_section.grid(row=1, column=0, sticky="ew", pady=(12, 0))
    options_section.columnconfigure(1, weight=1)

    ttk.Label(options_section, text="Capitalization").grid(row=0, column=0, sticky="w")
    ttk.Combobox(options_section, textvariable=text_transform_var, values=text_transform_options, state="readonly").grid(row=0, column=1, sticky="ew", padx=(12, 0))

    ttk.Label(options_section, text="Remove punctuation").grid(row=1, column=0, sticky="w", pady=(12, 0))
    ttk.Checkbutton(options_section, variable=remove_punctuation_var, onvalue=True, offvalue=False).grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(12, 0))

    setup_actions = ttk.Frame(setup_content)
    setup_actions.grid(row=2, column=0, sticky="ew", pady=(16, 0))
    setup_actions.columnconfigure(0, weight=1)
    setup_actions.columnconfigure(1, weight=1)
    ttk.Button(setup_actions, text="Start", command=start_studio).grid(row=0, column=0, sticky="ew")
    ttk.Label(setup_actions, textvariable=setup_status_var).grid(row=0, column=1, sticky="w", padx=(12, 0))

    refresh_all()
    setup_root.mainloop()

    if not selected_settings:
        return

    studio_root = tk.Tk()
    studio_root.focus_force()
    studio_root.attributes("-topmost", True)
    studio_root.title("OpenCaptions Studio " + version)
    studio_root.geometry("400x125")
    studio_root.minsize(400, 125)

    status_var = tk.StringVar()
    in_frame_var = tk.IntVar(value=-1)
    out_frame_var = tk.IntVar(value=-1)
    in_label_var = tk.StringVar(value="Not set")
    out_label_var = tk.StringVar(value="Not set")
    pending_process = {"previous_out_frame": None, "payload": None}

    def set_status(message):
        status_var.set(message)
        print(message)

    def mark_in():
        current_timeline = get_current_timeline()
        if not current_timeline:
            set_status("No active timeline.")
            return
        fps = get_timeline_fps(current_timeline)
        current_frame = get_current_timeline_frame(current_timeline)
        in_frame_var.set(current_frame)
        in_label_var.set(frame_to_timecode(current_frame, fps))
        set_status("IN marked.")

    def mark_out():
        current_timeline = get_current_timeline()
        if not current_timeline:
            set_status("No active timeline.")
            return
        fps = get_timeline_fps(current_timeline)
        current_frame = get_current_timeline_frame(current_timeline)
        out_frame_var.set(current_frame)
        out_label_var.set(frame_to_timecode(current_frame, fps))
        set_status("OUT marked.")

    def prepare_process_payload(current_timeline):
        if out_frame_var.get() < 0:
            fps = get_timeline_fps(current_timeline)
            current_frame = get_current_timeline_frame(current_timeline)
            out_frame_var.set(current_frame)
            out_label_var.set(frame_to_timecode(current_frame, fps))
        previous_out_frame = out_frame_var.get()
        payload = get_studio_range_payload(
            current_timeline,
            selected_settings["template_name"],
            selected_settings["subtitle_track_index"],
            selected_settings["video_track_index"],
            in_frame_var.get() if in_frame_var.get() >= 0 else None,
            out_frame_var.get() if out_frame_var.get() >= 0 else None,
            remove_punctuation=selected_settings["remove_punctuation"],
            text_transform=selected_settings["text_transform"],
        )
        return previous_out_frame, payload

    def finish_process(current_timeline, previous_out_frame, count):
        if count > 0:
            fps = get_timeline_fps(current_timeline)
            in_frame_var.set(previous_out_frame)
            in_label_var.set(frame_to_timecode(previous_out_frame, fps))
            out_frame_var.set(-1)
            out_label_var.set("Not set")
            set_status(f"Created merged Text+ clip from {count} subtitle item(s). OUT moved to IN.")
        else:
            set_status("No Text+ clip created.")

    def process_callback():
        payload = pending_process.get("payload")
        previous_out_frame = pending_process.get("previous_out_frame")
        if not payload:
            current_timeline = get_current_timeline()
            if not current_timeline:
                set_status("No active timeline.")
                return
            previous_out_frame, payload = prepare_process_payload(current_timeline)
        else:
            current_timeline = get_current_timeline()
            if not current_timeline:
                set_status("No active timeline.")
                return
        text_content = text_box.get("1.0", "end-1c")
        count = process_studio_payload(
            current_timeline,
            selected_settings["template_name"],
            selected_settings["video_track_index"],
            payload,
            text_content=text_content if text_content.strip() else None,
        )
        text_box.delete("1.0", "end")
        pending_process["previous_out_frame"] = None
        pending_process["payload"] = None
        finish_process(current_timeline, previous_out_frame, count)

    def process_text_box_return(event):
        process_callback()
        return "break"

    def load_process_text():
        current_timeline = get_current_timeline()
        if not current_timeline:
            set_status("No active timeline.")
            return
        previous_out_frame, payload = prepare_process_payload(current_timeline)
        if not payload:
            set_status("No text loaded.")
            return
        pending_process["previous_out_frame"] = previous_out_frame
        pending_process["payload"] = payload
        text_box.delete("1.0", "end")
        text_box.insert("1.0", payload["text"])
        text_box.focus_set()
        text_box.mark_set("insert", "end-1c")
        set_status(f"Loaded text from {payload['count']} subtitle item(s). Press Enter to create Text+.")

    studio_content = ttk.Frame(studio_root, padding=24)
    studio_content.grid(row=0, column=0, sticky="nsew")
    studio_root.columnconfigure(0, weight=1)
    studio_root.rowconfigure(0, weight=1)
    studio_content.columnconfigure(0, weight=1)

    time_frame = ttk.Frame(studio_content)
    time_frame.grid(row=0, column=0, sticky="ew")
    time_frame.columnconfigure(1, weight=1)
    time_frame.columnconfigure(3, weight=1)

    ttk.Label(time_frame, text="IN").grid(row=0, column=0, sticky="w")
    ttk.Label(time_frame, textvariable=in_label_var).grid(row=0, column=1, sticky="w", padx=(8, 24))
    ttk.Label(time_frame, text="OUT").grid(row=0, column=2, sticky="w")
    ttk.Label(time_frame, textvariable=out_label_var).grid(row=0, column=3, sticky="w", padx=(8, 0))

    text_box = tk.Text(studio_content, height=1, wrap="none", undo=True)
    text_box.bind("<Return>", process_text_box_return)
    text_box.grid(row=1, column=0, sticky="ew", pady=(12, 0))

    actions_frame = ttk.Frame(studio_content)
    actions_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))
    actions_frame.columnconfigure(0, weight=1)
    actions_frame.columnconfigure(1, weight=1)
    actions_frame.columnconfigure(2, weight=1)
    ttk.Button(actions_frame, text="IN", command=mark_in).grid(row=0, column=0, sticky="ew")
    ttk.Button(actions_frame, text="OUT", command=mark_out).grid(row=0, column=1, sticky="ew", padx=(12, 0))
    ttk.Button(actions_frame, text="Process", command=load_process_text).grid(row=0, column=2, sticky="ew", padx=(12, 0))

    studio_root.mainloop()

if __name__ == "__main__":
    main()