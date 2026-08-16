document.addEventListener("DOMContentLoaded", function () {
  const csrfToken = document
    .querySelector('meta[name="csrf-token"]')
    .getAttribute("content");

  const calendarEl = document.getElementById("shared-calendar");
  const token = calendarEl.dataset.token;
  const scheduleStartHour = Number(calendarEl.dataset.startHour || 6);
  const scheduleEndHour = Number(calendarEl.dataset.endHour || 22);

  const section = document.getElementById("confirmed-events-section");
  const list = document.getElementById("confirmed-events-list");

  function renderEvents(events) {
    if (!events.length) {
      section.classList.add("hidden");
      list.innerHTML = "";
      return;
    }
    section.classList.remove("hidden");
    list.innerHTML = events
      .map(function (e) {
        const loc = e.location_name ? ` @ ${e.location_name}` : "";
        const action = e.change_pending
          ? `<span class="pending">수정 요청 대기중</span>`
          : `<button type="button" class="copy-link-btn change-request-btn"
               data-event-id="${e.id}" data-date="${e.date}" data-start="${e.start_time}" data-end="${e.end_time}">수정 요청</button>`;
        return `<li><span>${e.date} ${e.start_time}~${e.end_time}${loc}</span>${action}</li>`;
      })
      .join("");
  }

  function refreshConfirmedEvents() {
    fetch(`/book/${token}/confirmed`)
      .then((res) => res.json())
      .then(renderEvents);
  }

  const modal = document.getElementById("request-modal");
  const current = document.getElementById("change-request-current");
  const form = document.getElementById("request-form");
  const dateField = document.getElementById("req-date");
  const startField = document.getElementById("req-start");
  const endPreview = document.getElementById("req-end-preview");
  const memoField = document.getElementById("req-memo");
  const cancelBtn = document.getElementById("req-cancel-btn");
  const successMsg = document.getElementById("request-success");
  const changeHint = document.getElementById("change-mode-hint");

  let changeEventId = null;
  let durationMin = 50;

  function addMinutes(timeStr, minutes) {
    const [h, m] = timeStr.split(":").map(Number);
    const total = (h * 60 + m + minutes + 1440) % 1440;
    return String(Math.floor(total / 60)).padStart(2, "0") + ":" + String(total % 60).padStart(2, "0");
  }
  function currentEnd() {
    return addMinutes(startField.value || "00:00", durationMin);
  }
  function updateEndPreview() {
    endPreview.textContent = startField.value ? `${durationMin}분 세션 → 종료 ${currentEnd()}` : "";
  }
  startField.addEventListener("change", updateEndPreview);
  startField.addEventListener("input", updateEndPreview);

  function todayStr() {
    const d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  dateField.min = todayStr();

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

  function exitChangeMode() {
    changeEventId = null;
    changeHint.classList.add("hidden");
  }

  function startChangeMode(eventId, date, start, end) {
    changeEventId = eventId;
    const [sh, sm] = start.split(":").map(Number);
    const [eh, em] = end.split(":").map(Number);
    durationMin = (eh * 60 + em) - (sh * 60 + sm);
    current.textContent = `현재 예약: ${date} ${start}~${end}`;
    changeHint.innerHTML =
      `<strong>${date} ${start}~${end}</strong> 예약을 변경하려고 해요. 아래 달력에서 원하는 날짜를 클릭해주세요. ` +
      `<button type="button" id="cancel-change-mode" class="copy-link-btn">변경 취소</button>`;
    changeHint.classList.remove("hidden");
    document.getElementById("cancel-change-mode").addEventListener("click", exitChangeMode);
    calendarEl.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  list.addEventListener("click", function (e) {
    const btn = e.target.closest(".change-request-btn");
    if (btn) startChangeMode(btn.dataset.eventId, btn.dataset.date, btn.dataset.start, btn.dataset.end);
  });

  setInterval(refreshConfirmedEvents, 20000);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") refreshConfirmedEvents();
  });

  const calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: "dayGridMonth",
    headerToolbar: {
      left: "prev,next today",
      center: "title",
      right: "dayGridMonth,timeGridWeek",
    },
    slotMinTime: String(scheduleStartHour).padStart(2, "0") + ":00:00",
    slotMaxTime: String(scheduleEndHour).padStart(2, "0") + ":00:00",
    eventSources: [
      { url: `/book/${token}/open-times` },
      { url: `/book/${token}/schedule/events` },
    ],
    eventClassNames: function (arg) {
      return arg.event.extendedProps.mine ? ["ev-mine"] : [];
    },
    eventClick: function (info) {
      const props = info.event.extendedProps;
      if (!props.mine) return;
      startChangeMode(info.event.id, props.date, props.start_time, props.end_time);
    },
    dateClick: function (info) {
      if (!changeEventId) {
        alert("먼저 위 목록이나 달력에서 변경할 내 예약을 선택해주세요.");
        return;
      }
      dateField.value = info.dateStr;
      startField.value = "10:00";
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
    fetch(`/book/${token}/events/${changeEventId}/change-request`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      body: JSON.stringify(payload),
    }).then((res) => {
      if (res.ok) {
        form.classList.add("hidden");
        successMsg.classList.remove("hidden");
        calendar.refetchEvents();
        refreshConfirmedEvents();
        exitChangeMode();
        setTimeout(closeModal, 1800);
      } else {
        res.json().then((data) => alert(data.error || data.description || "요청을 보내지 못했어요."));
      }
    });
  });
});
