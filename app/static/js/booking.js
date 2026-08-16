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
      `아래 달력에서 원하는 날짜를 클릭해주세요.` +
      ` <button type="button" id="cancel-change-mode" class="copy-link-btn">변경 취소</button>`;
    changeHint.classList.remove("hidden");
    document.getElementById("cancel-change-mode").addEventListener("click", exitChangeMode);
    calendarEl.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  function formatEventTime(date) {
    return String(date.getHours()).padStart(2, "0") + ":" + String(date.getMinutes()).padStart(2, "0");
  }

  const calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: "timeGridWeek",
    locale: "ko",
    headerToolbar: {
      left: "prev,next today",
      center: "title",
      right: "timeGridWeek,dayGridMonth",
    },
    validRange: { start: todayStr() },
    slotMinTime: String(scheduleStartHour).padStart(2, "0") + ":00:00",
    slotMaxTime: String(scheduleEndHour).padStart(2, "0") + ":00:00",
    eventSources: [
      { url: `/book/${token}/open-times` },
      { url: `/book/${token}/busy` },
      { url: `/book/${token}/my-events` },
    ],
    eventContent: function (arg) {
      if (arg.event.display === "background") return true;
      const time = formatEventTime(arg.event.start);
      return {
        html: `<div class="fc-event-compact"><span class="fc-event-compact-time">${time}</span><span class="fc-event-compact-title">${arg.event.title}</span></div>`,
      };
    },
    eventClassNames: function (arg) {
      return arg.event.extendedProps.mine ? ["ev-mine"] : [];
    },
    eventClick: function (info) {
      const props = info.event.extendedProps;
      if (!props.mine) return;
      window.startChangeMode({
        dataset: {
          eventId: info.event.id,
          date: props.date,
          start: props.start_time,
          end: props.end_time,
        },
      });
    },
    dateClick: function (info) {
      if (!changeEventId) {
        alert("먼저 위 목록이나 달력에서 변경할 내 예약을 선택해주세요.");
        return;
      }
      dateField.value = info.dateStr;
      startField.value = changeOriginal.start;
      memoField.value = "";
      updateEndPreview();
      openModal();
    },
  });
  calendar.render();

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
      memo: memoField.value,
    };
    const url = changeEventId ? `/book/${token}/events/${changeEventId}/change-request` : `/book/${token}/request`;
    fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify(payload),
    }).then((res) => {
      if (res.ok) {
        form.classList.add("hidden");
        successMsg.textContent = changeEventId
          ? "변경 요청을 보냈어요. 선생님이 확인 후 처리해요."
          : "요청이 접수되었습니다. 선생님 승인 후 확정됩니다.";
        successMsg.classList.remove("hidden");
        calendar.refetchEvents();
        if (changeEventId) {
          if (window.refreshConfirmedEvents) window.refreshConfirmedEvents();
          exitChangeMode();
        }
        setTimeout(closeModal, 1800);
      } else {
        res.json().then((data) => alert(data.error || data.description || "요청을 보내지 못했어요."));
      }
    });
  });
});
