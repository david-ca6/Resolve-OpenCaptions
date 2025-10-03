#!/usr/bin/env python3

from typing import List, Dict, Any

try:
    resolve
except NameError:
    from python_get_resolve import GetResolve
    resolve = GetResolve()

project_manager = resolve.GetProjectManager()
project = project_manager.GetCurrentProject()
timeline = project.GetCurrentTimeline()


def remove_ponctuation(text: str) -> str:
    ponctuation = [".", ","]
    for ponctuation in ponctuation:
        text = text.replace(ponctuation, "")
    return text


def apply_text_transform(text: str, transform: str) -> str:
    if transform == "Lowercase":
        return text.lower()
    if transform == "Uppercase":
        return text.upper()
    if transform == "Capitalize All Words":
        return text.title()
    return text


def timelineSubtitle2df(current_timeline, marker: str) -> List[Dict[str, Any]]:
    df: List[Dict[str, Any]] = []
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


def find_text_plus_template_by_name(media_pool, template_name: str):
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
    root_folder = media_pool.GetRootFolder()
    templates: List[str] = []

    def search_folder(folder, folder_path: str = ""):
        clips = folder.GetClipList()
        for clip in clips:
            if clip.GetClipProperty("File Path") == "":
                clip_name = clip.GetClipProperty("Clip Name")
                location = folder_path or "Root"
                templates.append(f"{clip_name} ({location})")
        for subfolder in folder.GetSubFolderList():
            subfolder_name = subfolder.GetName()
            new_path = f"{folder_path}/{subfolder_name}" if folder_path else subfolder_name
            search_folder(subfolder, new_path)

    search_folder(root_folder)
    if templates:
        print("Available Text+ templates:")
        for template in templates:
            print(f"  {template}")
    else:
        print("No Text+ templates found in Media Pool.")


def df2NewtimelineText(df: List[Dict[str, Any]], current_timeline, template_name: str, remove_punctuation: bool = True, text_transform: str = "Keep Case") -> bool:
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
    created_clips: List[Any] = []
    for row in df:
        if row["id"] == 0:
            continue
        start_frame = int(row["start"] * fps)
        end_frame = int(row["end"] * fps)
        duration = end_frame - start_frame
        new_clip = {
            "mediaPoolItem": text_clip,
            "startFrame": 0,
            "endFrame": duration - 1,
            "trackIndex": track_count,
            "recordFrame": start_frame,
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
                        text_content = remove_ponctuation(row["text"]) if remove_punctuation else row["text"]
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


def convert_subtitle_tracks(remove_punctuation: bool = True, text_transform: str = "Keep Case") -> int:
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


def main() -> None:
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
