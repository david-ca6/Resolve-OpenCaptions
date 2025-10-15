#!/usr/bin/env python3

import tkinter as tk
from tkinter import ttk, filedialog

version = "0.01.00"

# ------------------------- resolve api connection -------------------------

try:
    resolve # if we run inside Resolve, we already have the resolve object
except NameError:
    from python_get_resolve import GetResolve
    resolve = GetResolve()

project_manager = resolve.GetProjectManager()
project = project_manager.GetCurrentProject()
timeline = project.GetCurrentTimeline()

# ------------------------- srt file functions -------------------------

def readEncoding(file_path):
    with open(file_path, 'rb') as f:
        raw = f.read()

    for enc in ('utf-8-sig', 'utf-16', 'utf-32', 'cp1252'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError('unknown', raw, 0, len(raw),
                             "Unable to decode file with any of the supported encodings")

def srt2df(file_path):
    df = []

    content = readEncoding(file_path)

    subtitle_blocks = content.strip().split('\n\n')

    for block in subtitle_blocks:
        lines = block.split('\n')
        if len(lines) >= 3:

            nid = int(lines[0])

            timestamp = lines[1]
            text = '\n'.join(lines[2:])

            start_time = timestamp.split(' --> ')[0]
            end_time = timestamp.split(' --> ')[1]
            
            h, m, s = start_time.replace(',', '.').split(':')
            startTime_seconds = float(h) * 3600 + float(m) * 60 + float(s)

            h, m, s = end_time.replace(',', '.').split(':')
            endTime_seconds = float(h) * 3600 + float(m) * 60 + float(s)

            df.append({'id': nid, 'start': startTime_seconds, 'end': endTime_seconds, 'text': text})

    return df

def format_timestamp(seconds_value):
    total_milliseconds = int(round(float(seconds_value) * 1000))
    hours, remainder = divmod(total_milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def df2srt(df, file_path):
    with open(file_path, 'w', encoding='utf-8') as file:
        for row in df:

            nid = row['id']

            if nid == 0:
                continue
            
            start_time_str = format_timestamp(row['start'])
            end_time_str = format_timestamp(row['end'])

            file.write(f"{nid}\n")
            file.write(f"{start_time_str} --> {end_time_str}\n")
            file.write(f"{row['text']}\n\n")

def remove_punctuationText(text):
    punctuation = [".", ","]
    for mark in punctuation:
        text = text.replace(mark, "")
    return text

def apply_text_transform(text, transform):
    if transform == "Lowercase":
        return text.lower()
    elif transform == "Uppercase":
        return text.upper()
    elif transform == "Capitalize All Words":
        return text.title()
    else:
        return text

# ------------------------- resolve timeline functions -------------------------

def timelineText2df(timeline, marker):
    df = []
    if timeline:
        track_count = timeline.GetTrackCount("video")
        for i in range(1, track_count + 1):
            track = timeline.GetItemListInTrack("video", i)
            if track:
                track_name = timeline.GetTrackName("video", i)
                if track_name == marker:
                    nid = 1
                    for item in track:
                        if item.GetName() == "Text+":
                            start_time = item.GetStart() / timeline.GetSetting('timelineFrameRate')
                            end_time = item.GetEnd() / timeline.GetSetting('timelineFrameRate')
                            fusion_comp = item.GetFusionCompByIndex(1)
                            if fusion_comp:
                                text_tool = fusion_comp.FindToolByID("TextPlus")
                                if text_tool:
                                    text_content = text_tool.GetInput("StyledText")
                                    df.append({'id': nid, 'start': start_time, 'end': end_time, 'text': text_content})
                                    nid += 1
    return df

def timelineSubtitle2df(timeline, marker):
    df = []
    if timeline:
        track_count = timeline.GetTrackCount("subtitle")
        fps = float(timeline.GetSetting('timelineFrameRate'))
        for i in range(1, track_count + 1):
            track = timeline.GetItemListInTrack("subtitle", i)
            if track:
                track_name = timeline.GetTrackName("subtitle", i)
                if track_name == marker:
                    nid = 1
                    for item in track:
                        start_time = item.GetStart() / fps
                        end_time = item.GetEnd() / fps
                        text_content = item.GetName() or ""
                        df.append({'id': nid, 'start': start_time, 'end': end_time, 'text': text_content})
                        nid += 1
    return df

# ------------------------- srt file functions -------------------------

def df2timelineText(df, timeline, marker):
    if timeline:
        track_count = timeline.GetTrackCount("video")
        for i in range(1, track_count + 1):
            track = timeline.GetItemListInTrack("video", i)
            if track:
                track_name = timeline.GetTrackName("video", i)
                nid = 1
                if track_name == marker:
                    for item in track:
                        if item.GetName() == "Text+":
                            start_time = item.GetStart() / timeline.GetSetting('timelineFrameRate')
                            end_time = item.GetEnd() / timeline.GetSetting('timelineFrameRate')
                            fusion_comp = item.GetFusionCompByIndex(1)
                            if fusion_comp:
                                text_tool = fusion_comp.FindToolByID("TextPlus")
                                if text_tool:
                                    for row in df:
                                        if row['id'] == nid:
                                            text_tool.SetInput("StyledText", row['text'])
                                            nid += 1
                                            break

def df2NewtimelineText(df, timeline, template_name, remove_punctuation=True, text_transform="Keep Case"):
    """
    Create new Text+ clips from SRT dataframe on timeline
    
    Args:
        df: list of dicts with subtitle data
        timeline: DaVinci Resolve timeline object
        template_name: Name of the Text+ template to use
        remove_punctuation: Whether to remove punctuation from text
    """
    if not timeline or not df:
        print("No timeline or empty dataframe")
        return False

    print(f"Creating Text+ clips from SRT file: {df} using template: {template_name}")
    
    media_pool = project.GetMediaPool()
    root_folder = media_pool.GetRootFolder()
    
    text_clip = find_text_plus_template_by_name(media_pool, template_name)    
    if not text_clip:
        print(f"Text+ template '{template_name}' not found in Media Pool.")
        print("Available templates:")
        list_available_templates(media_pool)
        return False
    
    print(f"Found Text+ template: {text_clip.GetClipProperty('Clip Name')}")
    
    track_added = timeline.AddTrack("video")
    if not track_added:
        print("Failed to add new video track")
        return False
    
    track_count = timeline.GetTrackCount("video")
    
    fps = float(timeline.GetSetting('timelineFrameRate'))
    
    duration_multiplier = 1.0
    try:
        test_duration = 100
        test_clip = {
            "mediaPoolItem": text_clip,
            "startFrame": 0,
            "endFrame": test_duration - 1,
            "trackIndex": track_count,
            "recordFrame": 0
        }
        
        test_items = media_pool.AppendToTimeline([test_clip])
        if test_items and len(test_items) > 0:
            test_item = test_items[0]
            test_duration_real = test_item.GetDuration()
            timeline.DeleteClips([test_item], False)
            duration_multiplier = test_duration / test_duration_real if test_duration_real > 0 else 1.0
        
        print(f"Duration multiplier: {duration_multiplier:.3f}")
    except Exception as e:
        print(f"Warning: Could not calculate duration multiplier, using 1.0: {e}")
        duration_multiplier = 1.0
    
    created_clips = []
    
    for row in df:
        if row['id'] == 0:
            continue
            
        start_frame = int(row['start'] * fps)
        end_frame = int(row['end'] * fps)
        duration = end_frame - start_frame
        
        new_clip = {
            "mediaPoolItem": text_clip,
            "startFrame": 0,
            "endFrame": duration - 1,
            "trackIndex": track_count,
            "recordFrame": start_frame
        }
        
        base_duration = new_clip["endFrame"] - new_clip["startFrame"] + 1
        new_duration = int(base_duration * duration_multiplier + 0.999)
        new_clip["endFrame"] = new_duration - 1
        timeline_items = media_pool.AppendToTimeline([new_clip])
        
        if timeline_items and len(timeline_items) > 0:
            timeline_item = timeline_items[0]
            
            timeline_item.SetClipColor("Green")

            if timeline_item.GetFusionCompCount() > 0:
                comp = timeline_item.GetFusionCompByIndex(1)
                if comp:
                    text_tool = comp.FindToolByID("TextPlus")
                    if text_tool:
                        text_content = remove_punctuationText(row['text']) if remove_punctuation else row['text']
                        text_content = apply_text_transform(text_content, text_transform)
                        text_tool.SetInput("StyledText", text_content)
                        created_clips.append(timeline_item)
                        print(f"Created subtitle {row['id']}: {row['text'][:50]}{'...' if len(row['text']) > 50 else ''}")
                    else:
                        print(f"Warning: No TextPlus tool found in template for subtitle {row['id']}")
            else:
                print(f"Warning: No Fusion composition found for subtitle {row['id']}")
        else:
            print(f"Error: Failed to create timeline item for subtitle {row['id']}")

    
    print(f"Created {len(created_clips)} Text+ clips")
    return True

def find_text_plus_template_by_name(media_pool, template_name):
    """
    Find a specific Text+ template by name in the media pool
    Searches all folders for a matching template name
    """
    root_folder = media_pool.GetRootFolder()
    
    def search_folder(folder):
        clips = folder.GetClipList()
        for clip in clips:
            if clip.GetClipProperty("File Path") == "":
                clip_name = clip.GetClipProperty("Clip Name")
                if clip_name == template_name:
                    return clip
        
        for subfolder in folder.GetSubFolderList():
            result = search_folder(subfolder)
            if result:
                return result
        return None
    
    return search_folder(root_folder)

def list_available_templates(media_pool):
    """
    List all available Text+ templates (Fusion compositions) in the media pool
    """
    root_folder = media_pool.GetRootFolder()
    templates = []
    
    def search_folder(folder, folder_path=""):
        clips = folder.GetClipList()
        for clip in clips:
            if clip.GetClipProperty("File Path") == "":
                clip_name = clip.GetClipProperty("Clip Name")
                templates.append(f"  - {clip_name} (in {folder_path or 'Root'})")
        
        for subfolder in folder.GetSubFolderList():
            subfolder_name = subfolder.GetName()
            new_path = f"{folder_path}/{subfolder_name}" if folder_path else subfolder_name
            search_folder(subfolder, new_path)
    
    search_folder(root_folder)
    
    if templates:
        for template in templates:
            print(template)
    else:
        print("  No Text+ templates (Fusion compositions) found in Media Pool")
        print("  Create a Text+ composition in Fusion and save it to the Media Pool")

    # ------------------------------------------------------------

def get_video_tracks():
    global timeline
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return []
    track_count = timeline.GetTrackCount("video")
    return [timeline.GetTrackName("video", i) for i in range(1, track_count + 1)]

def get_subtitle_tracks():
    global timeline
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return []
    track_count = timeline.GetTrackCount("subtitle")
    return [timeline.GetTrackName("subtitle", i) for i in range(1, track_count + 1)]

def get_available_templates():
    """Get list of available Text+ templates from Media Pool"""
    try:
        media_pool = project.GetMediaPool()
        root_folder = media_pool.GetRootFolder()
        templates = []
        
        def search_folder(folder):
            for subfolder in folder.GetSubFolderList():
                if subfolder.GetName() == "Captions Templates":
                    clips = subfolder.GetClipList()
                    for clip in clips:
                        if clip.GetClipProperty("File Path") == "":
                            clip_name = clip.GetClipProperty("Clip Name")
                            templates.append(clip_name)
        
        search_folder(root_folder)

        templates.sort()

        return templates
    except Exception as e:
        print(f"Error getting templates: {e}")
        return []

def main():
    root = tk.Tk()
    root.focus_force()
    root.title("OpenCaptions " + version)
    root.geometry("720x540")
    root.minsize(720, 620)

    status_var = tk.StringVar()
    remove_punctuation_var = tk.BooleanVar(value=True)
    text_transform_options = ["Keep Case", "Lowercase", "Uppercase", "Capitalize All Words"]
    text_transform_var = tk.StringVar(value=text_transform_options[0])
    subtotext_remove_punctuation_var = tk.BooleanVar(value=True)
    subtotext_text_transform_var = tk.StringVar(value=text_transform_options[0])

    style = ttk.Style(root)
    style.configure("Delete.TButton", foreground="red")

    templates = get_available_templates()
    track_entries = []
    add_button = None
    export_track_var = tk.StringVar()
    export_path_var = tk.StringVar()
    export_combo = None
    exportsub_track_var = tk.StringVar()
    exportsub_path_var = tk.StringVar()
    exportsub_combo = None
    subtotext_track_var = tk.StringVar()
    subtotext_template_var = tk.StringVar(value=templates[0] if templates else "")
    subtotext_combo = None
    subtotext_template_combo = None

    def select_srt_file(entry):
        if entry not in track_entries:
            return
        path = filedialog.askopenfilename(title="Select SRT File", filetypes=[("SRT files", "*.srt"), ("All files", "*.*")])
        if path:
            entry["srt_var"].set(path)

    def select_export_file():
        path = filedialog.asksaveasfilename(title="Export SRT File", defaultextension=".srt", filetypes=[("SRT files", "*.srt"), ("All files", "*.*")])
        if path:
            export_path_var.set(path)

    def select_exportsub_file():
        path = filedialog.asksaveasfilename(title="Export SRT File", defaultextension=".srt", filetypes=[("SRT files", "*.srt"), ("All files", "*.*")])
        if path:
            exportsub_path_var.set(path)

    def remove_track_entry(entry):
        nonlocal add_button
        if entry not in track_entries:
            return
        for widget in (entry["label"], entry["template_combo"], entry["srt_entry"], entry["select_button"], entry["delete_button"]):
            widget.destroy()
        track_entries.remove(entry)
        for index, entry_item in enumerate(track_entries):
            entry_item["label"].configure(text=f"Track {index + 1}")
            entry_item["label"].grid_configure(row=index + 1)
            entry_item["template_combo"].grid_configure(row=index + 1)
            entry_item["srt_entry"].grid_configure(row=index + 1)
            entry_item["select_button"].grid_configure(row=index + 1)
            entry_item["delete_button"].grid_configure(row=index + 1)
        if add_button is not None:
            add_button.state(["!disabled"])
        status_var.set("Removed track.")

    def add_track_entry():
        nonlocal add_button
        if len(track_entries) >= 6:
            status_var.set("Maximum of 6 tracks.")
            if add_button is not None:
                add_button.state(["disabled"])
            return
        index = len(track_entries)
        template_var = tk.StringVar(value=templates[0] if templates else "")
        srt_var = tk.StringVar()
        entry = {
            "template_var": template_var,
            "srt_var": srt_var,
        }
        label = ttk.Label(tracks_frame, text=f"Track {index + 1}")
        label.grid(row=index + 1, column=0, sticky="w", pady=(4, 0))
        entry["label"] = label
        template_combo = ttk.Combobox(tracks_frame, textvariable=template_var, values=templates, state="readonly")
        template_combo.grid(row=index + 1, column=1, sticky="ew", pady=(4, 0))
        entry["template_combo"] = template_combo
        srt_entry = ttk.Entry(tracks_frame, textvariable=srt_var)
        srt_entry.grid(row=index + 1, column=2, sticky="ew", pady=(4, 0))
        entry["srt_entry"] = srt_entry
        select_button = ttk.Button(tracks_frame, text="Select", command=lambda e=entry: select_srt_file(e))
        select_button.grid(row=index + 1, column=3, sticky="w", pady=(4, 0))
        entry["select_button"] = select_button
        delete_button = ttk.Button(tracks_frame, text="X", width=1, style="Delete.TButton", command=lambda e=entry: remove_track_entry(e))
        delete_button.grid(row=index + 1, column=4, sticky="w", pady=(4, 0))
        entry["delete_button"] = delete_button
        track_entries.append(entry)
        if len(track_entries) == 6 and add_button is not None:
            add_button.state(["disabled"])

    def refresh_templates():
        nonlocal templates
        templates = get_available_templates()
        if templates:
            status_var.set(f"Found {len(templates)} templates")
        else:
            status_var.set("No Text+ templates found in Media Pool")
        for entry in track_entries:
            entry["template_combo"]["values"] = templates
            if templates:
                if entry["template_var"].get() not in templates:
                    entry["template_var"].set(templates[0])
            else:
                entry["template_var"].set("")
        if subtotext_template_combo is not None:
            subtotext_template_combo["values"] = templates
        if templates:
            if subtotext_template_var.get() not in templates:
                subtotext_template_var.set(templates[0])
        else:
            subtotext_template_var.set("")

    def refresh_export_tracks():
        nonlocal export_combo
        tracks = get_video_tracks()
        if export_combo is not None:
            export_combo["values"] = tracks
        if tracks:
            if export_track_var.get() not in tracks:
                export_track_var.set(tracks[0])
            status_var.set(f"Found {len(tracks)} Text+ tracks.")
        else:
            export_track_var.set("")
            status_var.set("No Text+ tracks available.")

    def refresh_exportsub_tracks():
        nonlocal exportsub_combo, subtotext_combo
        tracks = get_subtitle_tracks()
        if exportsub_combo is not None:
            exportsub_combo["values"] = tracks
        if subtotext_combo is not None:
            subtotext_combo["values"] = tracks
        if tracks:
            if exportsub_track_var.get() not in tracks:
                exportsub_track_var.set(tracks[0])
            if subtotext_track_var.get() not in tracks:
                subtotext_track_var.set(tracks[0])
            status_var.set(f"Found {len(tracks)} subtitle tracks.")
        else:
            exportsub_track_var.set("")
            subtotext_track_var.set("")
            status_var.set("No subtitle tracks available.")

    def execute_callback():
        if not track_entries:
            status_var.set("Add at least one track.")
            return
        for index, entry in enumerate(track_entries, start=1):
            if not entry["srt_var"].get() or not entry["template_var"].get():
                status_var.set(f"Track {index} is missing an SRT file or template.")
                return
        global timeline
        timeline = project.GetCurrentTimeline()
        for index, entry in enumerate(track_entries, start=1):
            df = srt2df(entry["srt_var"].get())
            success = df2NewtimelineText(
                df,
                timeline,
                entry["template_var"].get(),
                remove_punctuation=remove_punctuation_var.get(),
                text_transform=text_transform_var.get(),
            )
            if not success:
                status_var.set(f"Failed to create track {index}.")
                return
        status_var.set(f"Created {len(track_entries)} Text+ tracks.")

    def export_callback():
        if not export_track_var.get():
            status_var.set("Select a Text+ track to export.")
            return
        if not export_path_var.get():
            status_var.set("Select an SRT output file.")
            return
        global timeline
        timeline = project.GetCurrentTimeline()
        if not timeline:
            status_var.set("No active timeline.")
            return
        df = timelineText2df(timeline, export_track_var.get())
        if not df:
            status_var.set("No Text+ clips found on selected track.")
            return
        try:
            df2srt(df, export_path_var.get())
            status_var.set("Exported Text+ track.")
        except Exception as error:
            status_var.set("Failed to export Text+ track.")
            print(f"Error exporting Text+: {error}")

    def export_sub_callback():
        if not exportsub_track_var.get():
            status_var.set("Select a subtitle track to export.")
            return
        if not exportsub_path_var.get():
            status_var.set("Select an SRT output file.")
            return
        global timeline
        timeline = project.GetCurrentTimeline()
        if not timeline:
            status_var.set("No active timeline.")
            return
        df = timelineSubtitle2df(timeline, exportsub_track_var.get())
        if not df:
            status_var.set("No subtitles found on selected track.")
            return
        try:
            df2srt(df, exportsub_path_var.get())
            status_var.set("Exported subtitle track.")
        except Exception as error:
            status_var.set("Failed to export subtitle track.")
            print(f"Error exporting subtitle: {error}")

    def subtotext_callback():
        if not subtotext_track_var.get():
            status_var.set("Select a subtitle track.")
            return
        if not subtotext_template_var.get():
            status_var.set("Select a Text+ template.")
            return
        global timeline
        timeline = project.GetCurrentTimeline()
        if not timeline:
            status_var.set("No active timeline.")
            return
        df = timelineSubtitle2df(timeline, subtotext_track_var.get())
        if not df:
            status_var.set("No subtitles found on selected track.")
            return
        success = df2NewtimelineText(
            df,
            timeline,
            subtotext_template_var.get(),
            remove_punctuation=subtotext_remove_punctuation_var.get(),
            text_transform=subtotext_text_transform_var.get(),
        )
        if success:
            status_var.set("Created Text+ track from subtitles.")
        else:
            status_var.set("Failed to create Text+ track from subtitles.")

    content = ttk.Frame(root, padding=24)
    content.grid(row=0, column=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    content.columnconfigure(0, weight=1)
    content.rowconfigure(0, weight=1)

    notebook = ttk.Notebook(content)
    notebook.grid(row=0, column=0, sticky="nsew")

    create_tab = ttk.Frame(notebook)
    create_tab.columnconfigure(0, weight=1)
    notebook.add(create_tab, text="Create Text+")

    export_tab = ttk.Frame(notebook)
    export_tab.columnconfigure(0, weight=1)
    notebook.add(export_tab, text="Export Text+")

    subtotext_tab = ttk.Frame(notebook)
    subtotext_tab.columnconfigure(0, weight=1)
    notebook.add(subtotext_tab, text="Sub to Text+")

    exportsub_tab = ttk.Frame(notebook)
    exportsub_tab.columnconfigure(0, weight=1)
    notebook.add(exportsub_tab, text="Export Sub")

    tracks_section = ttk.LabelFrame(create_tab, text="Tracks", padding=(16, 12))
    tracks_section.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
    tracks_section.columnconfigure(1, weight=1)
    tracks_section.columnconfigure(2, weight=1)
    tracks_section.rowconfigure(0, weight=1)

    tracks_container = ttk.Frame(tracks_section, height=220)
    tracks_container.grid(row=0, column=0, columnspan=5, sticky="nsew")
    tracks_container.columnconfigure(0, weight=1)
    tracks_container.rowconfigure(0, weight=1)
    tracks_container.grid_propagate(False)

    tracks_frame = ttk.Frame(tracks_container)
    tracks_frame.grid(row=0, column=0, sticky="nsew")
    tracks_frame.columnconfigure(1, weight=1)
    tracks_frame.columnconfigure(2, weight=1)

    ttk.Label(tracks_frame, text="Track").grid(row=0, column=0, sticky="w", padx=(0, 8))
    ttk.Label(tracks_frame, text="Template").grid(row=0, column=1, sticky="w", padx=(0, 8))
    ttk.Label(tracks_frame, text="SRT File").grid(row=0, column=2, sticky="w", padx=(0, 8))
    ttk.Label(tracks_frame, text="Load File").grid(row=0, column=3, sticky="w", padx=(0, 8))
    ttk.Label(tracks_frame, text="Remove").grid(row=0, column=4, sticky="w")

    controls_frame = ttk.Frame(tracks_section)
    controls_frame.grid(row=1, column=0, columnspan=5, sticky="sew", pady=(12, 0))
    controls_frame.columnconfigure(0, weight=0)
    controls_frame.columnconfigure(1, weight=0)
    controls_frame.columnconfigure(2, weight=1)

    add_button = ttk.Button(controls_frame, text="Add Track", command=add_track_entry)
    add_button.grid(row=0, column=0, sticky="sw")
    ttk.Button(controls_frame, text="Refresh Templates", command=refresh_templates).grid(row=0, column=1, sticky="sw", padx=(12, 0))

    options_section = ttk.LabelFrame(create_tab, text="Options", padding=(16, 12))
    options_section.grid(row=1, column=0, sticky="ew")
    options_section.columnconfigure(1, weight=1)

    ttk.Label(options_section, text="Case").grid(row=0, column=0, sticky="w")
    ttk.Combobox(options_section, textvariable=text_transform_var, values=text_transform_options, state="readonly").grid(row=0, column=1, sticky="ew")
    ttk.Label(options_section, text="Remove punctuation").grid(row=1, column=0, sticky="w", pady=(12, 0))
    ttk.Checkbutton(options_section, variable=remove_punctuation_var, onvalue=True, offvalue=False).grid(row=1, column=1, sticky="w", pady=(12, 0))

    actions_frame = ttk.Frame(create_tab)
    actions_frame.grid(row=2, column=0, sticky="ew", pady=(16, 0))
    ttk.Button(actions_frame, text="Execute", command=execute_callback).grid(row=0, column=0, sticky="ew")
    actions_frame.columnconfigure(0, weight=1)

    subtotext_section = ttk.LabelFrame(subtotext_tab, text="Convert", padding=(16, 12))
    subtotext_section.grid(row=0, column=0, sticky="nsew")
    subtotext_section.columnconfigure(1, weight=1)

    ttk.Label(subtotext_section, text="Subtitle Track").grid(row=0, column=0, sticky="w")
    subtotext_combo = ttk.Combobox(subtotext_section, textvariable=subtotext_track_var, state="readonly")
    subtotext_combo.grid(row=0, column=1, sticky="ew")
    ttk.Button(subtotext_section, text="Refresh Tracks", command=refresh_exportsub_tracks).grid(row=0, column=2, sticky="w", padx=(12, 0))

    ttk.Label(subtotext_section, text="Template").grid(row=1, column=0, sticky="w", pady=(12, 0))
    subtotext_template_combo = ttk.Combobox(subtotext_section, textvariable=subtotext_template_var, values=templates, state="readonly")
    subtotext_template_combo.grid(row=1, column=1, sticky="ew", pady=(12, 0))
    ttk.Button(subtotext_section, text="Refresh Templates", command=refresh_templates).grid(row=1, column=2, sticky="w", padx=(12, 0), pady=(12, 0))

    subtotext_options = ttk.LabelFrame(subtotext_tab, text="Options", padding=(16, 12))
    subtotext_options.grid(row=1, column=0, sticky="ew", pady=(12, 0))
    subtotext_options.columnconfigure(1, weight=1)

    ttk.Label(subtotext_options, text="Case").grid(row=0, column=0, sticky="w")
    ttk.Combobox(subtotext_options, textvariable=subtotext_text_transform_var, values=text_transform_options, state="readonly").grid(row=0, column=1, sticky="ew")
    ttk.Label(subtotext_options, text="Remove punctuation").grid(row=1, column=0, sticky="w", pady=(12, 0))
    ttk.Checkbutton(subtotext_options, variable=subtotext_remove_punctuation_var, onvalue=True, offvalue=False).grid(row=1, column=1, sticky="w", pady=(12, 0))

    subtotext_actions = ttk.Frame(subtotext_tab)
    subtotext_actions.grid(row=2, column=0, sticky="ew", pady=(16, 0))
    ttk.Button(subtotext_actions, text="Convert", command=subtotext_callback).grid(row=0, column=0, sticky="ew")
    subtotext_actions.columnconfigure(0, weight=1)

    ttk.Label(
        subtotext_tab,
        text="This feature relies on a bug in the DaVinci Resolve API. If that bug gets fixed, all plugins that convert sub tracks to Text+ will break. Using a srt file is more reliable.",
        wraplength=480,
        foreground="orange"
    ).grid(row=3, column=0, sticky="w", pady=(12, 0))

    export_section = ttk.LabelFrame(export_tab, text="Export", padding=(16, 12))
    export_section.grid(row=0, column=0, sticky="nsew")
    export_section.columnconfigure(1, weight=1)

    ttk.Label(export_section, text="Text+ Track").grid(row=0, column=0, sticky="w")
    export_combo = ttk.Combobox(export_section, textvariable=export_track_var, state="readonly")
    export_combo.grid(row=0, column=1, sticky="ew")
    ttk.Button(export_section, text="Refresh Tracks", command=refresh_export_tracks).grid(row=0, column=2, sticky="w", padx=(12, 0))

    ttk.Label(export_section, text="SRT File").grid(row=1, column=0, sticky="w", pady=(12, 0))
    ttk.Entry(export_section, textvariable=export_path_var).grid(row=1, column=1, sticky="ew", pady=(12, 0))
    ttk.Button(export_section, text="Select", command=select_export_file).grid(row=1, column=2, sticky="w", padx=(12, 0), pady=(12, 0))

    ttk.Button(export_section, text="Export", command=export_callback).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(24, 0))

    exportsub_section = ttk.LabelFrame(exportsub_tab, text="Export", padding=(16, 12))
    exportsub_section.grid(row=0, column=0, sticky="nsew")
    exportsub_section.columnconfigure(1, weight=1)

    ttk.Label(exportsub_section, text="Subtitle Track").grid(row=0, column=0, sticky="w")
    exportsub_combo = ttk.Combobox(exportsub_section, textvariable=exportsub_track_var, state="readonly")
    exportsub_combo.grid(row=0, column=1, sticky="ew")
    ttk.Button(exportsub_section, text="Refresh Tracks", command=refresh_exportsub_tracks).grid(row=0, column=2, sticky="w", padx=(12, 0))

    ttk.Label(exportsub_section, text="SRT File").grid(row=1, column=0, sticky="w", pady=(12, 0))
    ttk.Entry(exportsub_section, textvariable=exportsub_path_var).grid(row=1, column=1, sticky="ew", pady=(12, 0))
    ttk.Button(exportsub_section, text="Select", command=select_exportsub_file).grid(row=1, column=2, sticky="w", padx=(12, 0), pady=(12, 0))

    ttk.Button(exportsub_section, text="Export", command=export_sub_callback).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(24, 0))

    ttk.Label(
        exportsub_section,
        text="This feature relies on a bug in the DaVinci Resolve API. If that bug gets fixed, all plugins that convert sub tracks to Text+ will break. Using a srt file is more reliable.",
        wraplength=480,
        foreground="orange"
    ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 0))

    status_frame = ttk.Frame(content)
    status_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
    status_lbl = ttk.Label(status_frame, textvariable=status_var)
    status_lbl.grid(row=0, column=0, sticky="w")

    add_track_entry()
    refresh_templates()
    refresh_export_tracks()
    refresh_exportsub_tracks()

    root.mainloop()

if __name__ == "__main__":
    main()