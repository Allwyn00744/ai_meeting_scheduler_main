import { api } from "./client";
import type { MeetingNoteRecord } from "@/types";

export const meetingTranscriptApi = {
  upload: (
    meetingId: number,
    file: File,
    onProgress?: (percent: number) => void
  ) => {
    const formData = new FormData();
    formData.append("file", file);

    return api
      .post<MeetingNoteRecord>(
        `/meeting-intelligence/transcript/${meetingId}`,
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
          onUploadProgress: (event) => {
            if (!onProgress || !event.total) return;
            onProgress(Math.round((event.loaded / event.total) * 100));
          },
        }
      )
      .then((r) => r.data);
  },
};
