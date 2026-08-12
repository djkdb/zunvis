import EventKit
import Foundation

/// EventKit으로 오늘 일정을 읽는다.
///
/// AppleScript로 Calendar.app에 묻는 것은 수 초가 걸린다. EventKit은 즉시다.
/// 이것이 동작하면 Python의 `MacCalendarAdapter`를 이 헬퍼로 교체한다.
enum CalendarQuery {
    static func today() {
        let store = EKEventStore()
        let semaphore = DispatchSemaphore(value: 0)
        var granted = false

        let handler: (Bool, Error?) -> Void = { ok, _ in
            granted = ok
            semaphore.signal()
        }
        if #available(macOS 14.0, *) {
            store.requestFullAccessToEvents(completion: handler)
        } else {
            store.requestAccess(to: .event, completion: handler)
        }
        semaphore.wait()

        guard granted else {
            emit(.error(message: "캘린더 권한이 없습니다 (시스템 설정 → 개인정보 보호 → 캘린더)"))
            return
        }

        let calendar = Calendar.current
        let start = calendar.startOfDay(for: Date())
        guard let end = calendar.date(byAdding: .day, value: 1, to: start) else { return }

        let predicate = store.predicateForEvents(
            withStart: start, end: end, calendars: nil
        )
        let formatter = ISO8601DateFormatter()
        let events = store.events(matching: predicate).map { event -> [String: Any] in
            [
                "title": event.title ?? "",
                "starts_at": formatter.string(from: event.startDate),
                "location": event.location ?? "",
                "all_day": event.isAllDay,
            ]
        }

        guard
            let data = try? JSONSerialization.data(
                withJSONObject: ["type": "calendar", "events": events],
                options: [.withoutEscapingSlashes]
            ),
            let line = String(data: data, encoding: .utf8)
        else { return }
        print(line)
    }
}
