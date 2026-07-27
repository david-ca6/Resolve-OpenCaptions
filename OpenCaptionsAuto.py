#!/usr/bin/env python3

version = "0.01.02"
TEMPLATES_FOLDER_NAME = "Captions Templates"

try:
    resolve # if we run inside Resolve, we already have the resolve object
except NameError:
    from python_get_resolve import GetResolve
    resolve = GetResolve()

project_manager = resolve.GetProjectManager()
project = project_manager.GetCurrentProject()
timeline = project.GetCurrentTimeline()


def remove_punctuationText(text):
    punctuation = [".", ","]
    for mark in punctuation:
        text = text.replace(mark, "")
    return text


def apply_text_transform(text, transform):
    if transform == "Lowercase":
        return text.lower()
    if transform == "Uppercase":
        return text.upper()
    if transform == "Capitalize All Words":
        return text.title()
    return text


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


def timelineSubtitle2df(current_timeline, marker):
    df = []
    if current_timeline:
        track_count = current_timeline.GetTrackCount("subtitle")
        fps = float(current_timeline.GetSetting("timelineFrameRate"))
        for index in range(1, track_count + 1):
            track = current_timeline.GetItemListInTrack("subtitle", index)
            if track:
                track_name = current_timeline.GetTrackName("subtitle", index)
                if track_name == marker:
                    nid = 1
                    for item in track:
                        start_time = item.GetStart() / fps
                        end_time = item.GetEnd() / fps
                        text_content = item.GetName() or ""
                        df.append({"id": nid, "start": start_time, "end": end_time, "text": text_content})
                        nid += 1
    return df


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


def append_text_plus_with_duration(media_pool, current_timeline, text_clip, track_index, record_frame, target_duration, duration_multiplier):
    """
    Append a Text+ clip and make sure it occupies exactly target_duration
    timeline frames.

    On fractional frame rates (23.976/29.97/59.94) Resolve can place the
    clip one frame shorter than requested, leaving flickering 1-frame gaps
    between captions, so the placed length is verified and corrected.
    """
    source_duration = max(1, int(target_duration * duration_multiplier + 0.999))
    attempts = 4
    for attempt in range(attempts):
        new_clip = {
            "mediaPoolItem": text_clip,
            "startFrame": 0,
            "endFrame": source_duration - 1,
            "trackIndex": track_index,
            "recordFrame": record_frame,
        }
        timeline_items = media_pool.AppendToTimeline([new_clip])
        if not timeline_items or len(timeline_items) == 0:
            return None
        timeline_item = timeline_items[0]
        adjustment = target_duration - int(timeline_item.GetDuration())
        adjusted_source_duration = max(1, source_duration + adjustment)
        if adjustment == 0 or adjusted_source_duration == source_duration or attempt == attempts - 1:
            return timeline_item
        current_timeline.DeleteClips([timeline_item], False)
        source_duration = adjusted_source_duration
    return None


def snap_caption_frame_ranges(df, fps):
    """
    Convert caption times to frame ranges, closing the 1-frame gaps that
    rounding fractional frame rates can leave between consecutive captions.
    """
    frame_ranges = []
    for row in df:
        start_frame = int(round(row["start"] * fps))
        end_frame = int(round(row["end"] * fps))
        frame_ranges.append([start_frame, end_frame])
    for current_range, next_range in zip(frame_ranges, frame_ranges[1:]):
        if 0 < next_range[0] - current_range[1] <= 1:
            current_range[1] = next_range[0]
    return frame_ranges


def df2NewtimelineText(df, current_timeline, template_name, remove_punctuation=True, text_transform="Keep Case"):
    if not current_timeline or not df:
        print(f"No timeline or empty subtitles for template {template_name}.")
        return False
    media_pool = project.GetMediaPool()
    text_clip = find_text_plus_template_by_name(media_pool, template_name)
    if not text_clip:
        print(f"Text+ template {template_name} not found in Media Pool.")
        list_available_templates(media_pool)
        return False
    print(f"Creating Text+ track for template {template_name}.")
    track_added = current_timeline.AddTrack("video")
    if not track_added:
        print(f"Could not add video track for template {template_name}.")
        return False
    track_count = current_timeline.GetTrackCount("video")
    fps = float(current_timeline.GetSetting("timelineFrameRate"))
    duration_multiplier = 1.0
    try:
        test_duration = 100
        test_clip = {
            "mediaPoolItem": text_clip,
            "startFrame": 0,
            "endFrame": test_duration - 1,
            "trackIndex": track_count,
            "recordFrame": 0,
        }
        test_items = media_pool.AppendToTimeline([test_clip])
        if test_items and len(test_items) > 0:
            test_item = test_items[0]
            test_duration_real = test_item.GetDuration()
            current_timeline.DeleteClips([test_item], False)
            duration_multiplier = test_duration / test_duration_real if test_duration_real > 0 else 1.0
        print(f"Duration multiplier for {template_name}: {duration_multiplier:.3f}")
    except Exception as error:
        print(f"Warning: could not calculate duration multiplier for {template_name}: {error}")
        duration_multiplier = 1.0
    created_clips = []
    rows = [row for row in df if row["id"] != 0]
    frame_ranges = snap_caption_frame_ranges(rows, fps)
    for row, (start_frame, end_frame) in zip(rows, frame_ranges):
        duration = max(1, end_frame - start_frame)
        timeline_item = append_text_plus_with_duration(
            media_pool,
            current_timeline,
            text_clip,
            track_count,
            start_frame,
            duration,
            duration_multiplier,
        )
        if timeline_item:
            timeline_item.SetClipColor("Green")
            if timeline_item.GetFusionCompCount() > 0:
                comp = timeline_item.GetFusionCompByIndex(1)
                if comp:
                    text_tool = comp.FindToolByID("TextPlus")
                    if text_tool:
                        text_content = remove_punctuationText(row["text"]) if remove_punctuation else row["text"]
                        text_content = apply_text_transform(text_content, text_transform)
                        text_tool.SetInput("StyledText", text_content)
                        created_clips.append(timeline_item)
                        preview = row["text"][:50]
                        suffix = "..." if len(row["text"]) > 50 else ""
                        print(f"Created subtitle {row['id']} for {template_name}: {preview}{suffix}")
                    else:
                        print(f"Warning: no TextPlus tool found in template {template_name}.")
                else:
                    print(f"Warning: no Fusion composition found in template {template_name}.")
            else:
                print(f"Warning: created clip has no Fusion composition for template {template_name}.")
        else:
            print(f"Error: failed to create timeline item for subtitle {row['id']} in template {template_name}.")
    print(f"Created {len(created_clips)} clips for template {template_name}.")
    return bool(created_clips)


def convert_subtitle_tracks(remove_punctuation=True, text_transform="Keep Case"):
    global timeline
    timeline = project.GetCurrentTimeline()
    if not timeline:
        print("No active timeline.")
        return 0
    track_count = timeline.GetTrackCount("subtitle")
    if track_count == 0:
        print("No subtitle tracks found.")
        return 0
    success = 0
    for index in range(1, track_count + 1):
        track_name = timeline.GetTrackName("subtitle", index)
        if not track_name:
            continue
        df = timelineSubtitle2df(timeline, track_name)
        if not df:
            print(f"Subtitle track {track_name} is empty.")
            continue
        created = df2NewtimelineText(df, timeline, track_name, remove_punctuation, text_transform)
        if created:
            success += 1
    return success


def main():
    global project
    current_project = project_manager.GetCurrentProject()
    if not current_project:
        print("No active project.")
        return
    project = current_project
    conversions = convert_subtitle_tracks()
    if conversions > 0:
        print(f"Created {conversions} Text+ track(s).")
    else:
        print("No Text+ tracks created.")


if __name__ == "__main__":
    main()
