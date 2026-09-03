/** Calendar read (design §4.4). Only start/end/coarse type leave the device. */
import * as Calendar from "expo-calendar";
import { api, CalendarEventIn, isoDate } from "../lib/api";

const TRAVEL_WORDS = /\b(flight|train|drive|travel|airport|טיסה|נסיעה)\b/i;

function coarseType(e: Calendar.Event): CalendarEventIn["coarse_type"] {
  if (TRAVEL_WORDS.test(e.title ?? "")) return "travel";
  if (e.availability === Calendar.Availability.FREE) return "personal";
  if (e.allDay) return "personal";
  return "meeting";
}

/** Reads today's events from every visible calendar and uploads the coarse shape. */
export async function syncTodayCalendar(date: Date = new Date()): Promise<number> {
  const { status } = await Calendar.requestCalendarPermissionsAsync();
  if (status !== "granted") return 0;
  const calendars = await Calendar.getCalendarsAsync(Calendar.EntityTypes.EVENT);
  const start = new Date(date);
  start.setHours(0, 0, 0, 0);
  const end = new Date(date);
  end.setHours(23, 59, 59, 999);
  const events = await Calendar.getEventsAsync(
    calendars.map((c) => c.id),
    start,
    end,
  );
  const coarse: CalendarEventIn[] = events
    .filter((e) => !e.allDay)
    .map((e) => ({
      start: new Date(e.startDate).toISOString(),
      end: new Date(e.endDate).toISOString(),
      coarse_type: coarseType(e),
    }));
  await api.putCalendar(isoDate(date), coarse);
  return coarse.length;
}
