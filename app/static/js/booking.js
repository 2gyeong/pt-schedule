document.addEventListener("DOMContentLoaded", function () {
  const csrfToken = document
    .querySelector('meta[name="csrf-token"]')
    .getAttribute("content");

  const calendarEl = document.getElementById("calendar");
  const token = calendarEl.dataset.token;
  const scheduleStartHour = Number(calendarEl.dataset.startHour || 6);
  const scheduleEndHour = Number(calendarEl.dataset.endHour || 22);

  const DEFAULT_DURATION_MIN = 50;

  const modal = document.getElementById("request-modal");
  const form = document.getElementById("request-form");
  const dateField = document.getElementById("req-date");
  const startField = document.getElementById("req-start");
  const endPreview = document.getElementById("req-end-preview");
  const locationField = document.getElementById("req-location");
  const memoField = document.getElementById("req-memo");
  const cancelBtn = document.getElementById("req-cancel-btn");
  const successMsg = document.getElementById("request-success");
  const changeHint = document.getElementById("change-mode-hint");

  let changeEventId = null;
  let changeOriginal = null;
  let durationMin = DEFAULT_DURATION_MIN;

  function addMinutes(timeStr, minutes) {
    const [h, m] = timeStr.split(":").map(Number);
    const total = (h * 60 + m + minutes + 1440) % 1440;
    return String(Math.floor(total / 60)).padStart(2, "0") + ":" + String(total % 60).padStart(2, "0");
  }

  function currentEnd() {
    return addMinutes(startField.value || "00:00", durationMin);
  }

  function updateEndPreview() {
    endPreview.textContent = startField.value
      ? `${durationMin}분 세션 → 종료 ${currentEnd()}`
      : "";
  }
  startField.addEventListener("change", updateEndPreview);
  startField.addEventListener("input", updateEndPreview);

  function openModal() {
    successMsg.classList.add("hidden");
    form.classList.remove("hidden");
    modal.classList.remove("hidden");
  }
  function closeModal() {
    modal.classList.add("hidden");
    form.reset();
  }
  cancelBtn.addEventListener("click", closeModal);

  function todayStr() {
    const d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  dateField.min = todayStr();

  function exitChangeMode() {
    changeEventId = null;
    changeOriginal = null;
    durationMin = DEFAULT_DURATION_MIN;
    changeHint.classList.add("hidden");
  }

  window.startChangeMode = function (btn) {
    changeEventId = btn.dataset.eventId;
    changeOriginal = { date: btn.dataset.date, start: btn.dataset.start, end: btn.dataset.end };
    const [sh, sm] = changeOriginal.start.split(":").map(Number);
    const [eh, em] = changeOriginal.end.split(":").map(Number);
    durationMin = (eh * 60 + em) - (sh * 60 + sm);
    changeHint.innerHTML =
      `<strong>${changeOriginal.date} ${changeOriginal.start}~${changeOriginal.end}</strong> 예약을 변경하려고 해요. ` +
      `아래 달력에서 원하는 날짜를 클릭하거나, 예약 블록을 직접 끌어다 놓아도 돼요.` +
      ` <button type="button" id="cancel-change-mode" class="copy-link-btn">변경 취소</button>`;
    changeHint.classList.remove("hidden");
    document.getElementById("cancel-change-mode").addEventListener("click", exitChangeMode);
    calendarEl.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  function formatEventTime(date) {
    return String(date.getHours()).padStart(2, "0") + ":" + String(date.getMinutes()).padStart(2, "0");
  }

  function toDateStr(d) {
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  function mondayOfCurrentWeek() {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    const day = d.getDay(); // 0=일 ... 6=토
    const diffToMonday = (day + 6) % 7;
    d.setDate(d.getDate() - diffToMonday);
    return d;
  }
  const currentWeekStart = mondayOfCurrentWeek();
  const currentWeekEnd = new Date(currentWeekStart);
  currentWeekEnd.setDate(currentWeekStart.getDate() + 7);

  const calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: "timeGridWeek",
    locale: "ko",
    hiddenDays: [0],
    headerToolbar: {
      left: "prev,next today",
      center: "title",
      right: "timeGridWeek,dayGridMonth",
    },
    editable: true,
    eventDurationEditable: false,
    slotMinTime: String(scheduleStartHour).padStart(2, "0") + ":00:00",
    slotMaxTime: String(scheduleEndHour).padStart(2, "0") + ":00:00",
    eventSources: [
      { url: `/book/${token}/open-times` },
      { url: `/book/${token}/busy` },
      { url: `/book/${token}/my-events` },
    ],
    eventDataTransform: function (raw) {
      if (raw.extendedProps) {
        raw.startEditable = !!(raw.extendedProps.mine && raw.extendedProps.confirmed);
      }
      return raw;
    },
    dayCellClassNames: function (arg) {
      return arg.date >= currentWeekStart && arg.date < currentWeekEnd ? ["fc-current-week"] : [];
    },
    eventContent: function (arg) {
      if (arg.event.display === "background") return true;
      const time = formatEventTime(arg.event.start);
      return {
        html: `<div class="fc-event-compact"><span class="fc-event-compact-time">${time}</span><span class="fc-event-compact-title">${arg.event.title}</span></div>`,
      };
    },
    eventClassNames: function (arg) {
      const classes = arg.event.extendedProps.mine ? ["ev-mine"] : [];
      if (arg.event.extendedProps.mine && !arg.event.extendedProps.confirmed) classes.push("ev-pending");
      return classes;
    },
    eventClick: function (info) {
      const props = info.event.extendedProps;
      if (!props.mine || !props.confirmed) return;
      window.startChangeMode({
        dataset: {
          eventId: info.event.id,
          date: props.date,
          start: props.start_time,
          end: props.end_time,
        },
      });
    },
    eventDrop: function (info) {
      const props = info.event.extendedProps;
      if (!props.mine || !props.confirmed) {
        info.revert();
        return;
      }
      if (!confirm("이 시간으로 변경 요청할까요?")) {
        info.revert();
        return;
      }
      const start = info.event.start;
      const end = info.event.end;
      const eventId = info.event.id;
      // 드래그는 요청을 접수할 뿐 바로 확정 이동되는 게 아니므로, 실제 블록은 원래 자리로 되돌린다.
      info.revert();
      fetch(`/book/${token}/events/${eventId}/change-request`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        body: JSON.stringify({
          date: toDateStr(start),
          start_time: formatEventTime(start),
          end_time: formatEventTime(end),
        }),
      }).then((res) => {
        if (res.ok) {
          calendar.refetchEvents();
          alert("변경 요청을 보냈어요. 선생님이 확인 후 처리해요.");
        } else {
          res.json().then((data) => alert(data.error || data.description || "요청을 보내지 못했어요."));
        }
      });
    },
    dateClick: function (info) {
      if (!changeEventId) {
        alert("먼저 위 달력에서 변경할 내 예약을 클릭해주세요.");
        return;
      }
      dateField.value = info.dateStr;
      startField.value = changeOriginal.start;
      memoField.value = "";
      locationField.value = "";
      updateEndPreview();
      openModal();
    },
  });
  calendar.render();
  window.ptBookingCalendar = calendar;

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    const selected = new Date(`${dateField.value}T${startField.value}`);
    if (selected < new Date()) {
      alert("지난 날짜/시간에는 요청할 수 없어요.");
      return;
    }
    const payload = {
      date: dateField.value,
      start_time: startField.value,
      end_time: currentEnd(),
      location_id: locationField.value || null,
      memo: memoField.value,
    };
    fetch(`/book/${token}/events/${changeEventId}/change-request`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify(payload),
    }).then((res) => {
      if (res.ok) {
        form.classList.add("hidden");
        successMsg.textContent = "변경 요청을 보냈어요. 선생님이 확인 후 처리해요.";
        successMsg.classList.remove("hidden");
        calendar.refetchEvents();
        exitChangeMode();
        setTimeout(closeModal, 1800);
      } else {
        res.json().then((data) => alert(data.error || data.description || "요청을 보내지 못했어요."));
      }
    });
  });
});
