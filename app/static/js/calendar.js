document.addEventListener("DOMContentLoaded", function () {
  const csrfToken = document
    .querySelector('meta[name="csrf-token"]')
    .getAttribute("content");

  const scheduleStartHour = Number(document.getElementById("calendar").dataset.startHour || 6);
  const scheduleEndHour = Number(document.getElementById("calendar").dataset.endHour || 22);
  const roundStartDate = document.getElementById("calendar").dataset.roundStart || null;

  const modal = document.getElementById("event-modal");
  const form = document.getElementById("event-form");
  const modalTitle = document.getElementById("modal-title");
  const idField = document.getElementById("event-id");
  const typeField = document.getElementById("event-type");
  const memberField = document.getElementById("event-member");
  const memberFieldWrap = document.getElementById("event-member-field");
  const prospectField = document.getElementById("event-prospect-field");
  const prospectNameField = document.getElementById("event-prospect-name");
  const locationField = document.getElementById("event-location");
  const dateField = document.getElementById("event-date");
  const startField = document.getElementById("event-start");
  const endField = document.getElementById("event-end");
  const statusField = document.getElementById("event-status");
  const statusFieldWrap = document.getElementById("event-status-field");
  const memoField = document.getElementById("event-memo");
  const deleteBtn = document.getElementById("delete-btn");
  const cancelBtn = document.getElementById("cancel-btn");
  const cancelBtn2 = document.getElementById("cancel-btn-2");
  const normalActions = document.getElementById("normal-actions");
  const requestActions = document.getElementById("request-actions");
  const approveBtn = document.getElementById("approve-btn");
  const rejectBtn = document.getElementById("reject-btn");

  function openModal() {
    modal.classList.remove("hidden");
  }
  function closeModal() {
    modal.classList.add("hidden");
    form.reset();
    idField.value = "";
  }
  cancelBtn.addEventListener("click", closeModal);
  cancelBtn2.addEventListener("click", closeModal);

  function addMinutes(timeStr, minutes) {
    const [h, m] = timeStr.split(":").map(Number);
    const total = (h * 60 + m + minutes + 1440) % 1440;
    return String(Math.floor(total / 60)).padStart(2, "0") + ":" + String(total % 60).padStart(2, "0");
  }

  function durationForType() {
    return typeField.value === "상담" ? 30 : 50;
  }

  function setStartTime(time) {
    startField.value = time;
    endField.value = addMinutes(time, durationForType());
    document.querySelectorAll(".time-cube").forEach(function (cube) {
      cube.classList.toggle("selected", cube.dataset.time === time);
    });
  }
  startField.addEventListener("change", function () {
    if (startField.value) {
      endField.value = addMinutes(startField.value, durationForType());
      document.querySelectorAll(".time-cube").forEach(function (cube) {
        cube.classList.toggle("selected", cube.dataset.time === startField.value);
      });
    }
  });
  function toggleMemberFields() {
    const isConsult = typeField.value === "상담";
    memberFieldWrap.classList.toggle("hidden", isConsult);
    prospectField.classList.toggle("hidden", !isConsult);
    memberField.required = !isConsult;
    prospectNameField.required = isConsult;
  }
  typeField.addEventListener("change", function () {
    if (startField.value) endField.value = addMinutes(startField.value, durationForType());
    toggleMemberFields();
  });

  const cubeContainer = document.getElementById("event-time-cubes");
  for (let h = scheduleStartHour; h < scheduleEndHour; h++) {
    const time = String(h).padStart(2, "0") + ":00";
    const cube = document.createElement("button");
    cube.type = "button";
    cube.className = "time-cube";
    cube.dataset.time = time;
    cube.textContent = time;
    cube.addEventListener("click", function () {
      setStartTime(time);
    });
    cubeContainer.appendChild(cube);
  }

  function todayStr() {
    const d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  function openCreateModal(dateStr) {
    modalTitle.textContent = "일정 등록";
    idField.value = "";
    typeField.value = "PT";
    prospectNameField.value = "";
    toggleMemberFields();
    locationField.value = "";
    dateField.value = dateStr;
    setStartTime("10:00");
    statusField.value = "확정";
    normalActions.classList.remove("hidden");
    requestActions.classList.add("hidden");
    statusFieldWrap.classList.remove("hidden");
    deleteBtn.classList.add("hidden");
    openModal();
  }

  document.getElementById("new-event-btn").addEventListener("click", function () {
    openCreateModal(todayStr());
  });

  let selectedMemberId = "";
  const AVAILABILITY_SOURCE_ID = "member-availability";
  const DRAG_AVAILABILITY_SOURCE_ID = "drag-availability";

  function showCalendarFlash(message) {
    const flash = document.getElementById("reassign-flash");
    if (!flash) return;
    flash.innerHTML = message ? `<ul class="flash"><li>${message}</li></ul>` : "";
  }

  const holidaysEl = document.getElementById("kr-holidays");
  const KR_HOLIDAYS = holidaysEl ? JSON.parse(holidaysEl.textContent) : {};

  function toDateStr(d) {
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  const weekLabelEl = document.getElementById("calendar-week-label");
  function updateWeekLabel(info) {
    if (info.view.type !== "timeGridWeek") {
      weekLabelEl.textContent = "";
      return;
    }
    const sunday = info.start;
    const month = sunday.getMonth() + 1;
    const week = Math.floor((sunday.getDate() - 1) / 7) + 1;
    weekLabelEl.textContent = `${month}월 ${week}주차`;
  }

  function formatEventTime(date) {
    return String(date.getHours()).padStart(2, "0") + ":" + String(date.getMinutes()).padStart(2, "0");
  }

  const calendarEl = document.getElementById("calendar");
  const calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: "timeGridWeek",
    initialDate: roundStartDate || undefined,
    locale: "ko",
    headerToolbar: {
      left: "prev,next today",
      center: "title",
      right: "timeGridWeek,dayGridMonth",
    },
    datesSet: updateWeekLabel,
    slotMinTime: String(scheduleStartHour).padStart(2, "0") + ":00:00",
    slotMaxTime: String(scheduleEndHour).padStart(2, "0") + ":00:00",
    snapDuration: "00:10:00",
    eventDurationEditable: false,
    eventContent: function (arg) {
      if (arg.event.display === "background") return true;
      const time = formatEventTime(arg.event.start);
      const color = arg.event.backgroundColor || arg.event.borderColor || "#888";
      const dot = arg.view.type === "dayGridMonth"
        ? `<span class="fc-event-compact-dot" style="background:${color}"></span>`
        : "";
      return {
        html: `<div class="fc-event-compact">${dot}<span class="fc-event-compact-time">${time}</span><span class="fc-event-compact-title">${arg.event.title}</span></div>`,
      };
    },
    dayCellClassNames: function (arg) {
      return KR_HOLIDAYS[toDateStr(arg.date)] ? ["fc-holiday"] : [];
    },
    dayCellContent: function (arg) {
      if (arg.view.type !== "dayGridMonth") return arg.dayNumberText;
      const name = KR_HOLIDAYS[toDateStr(arg.date)];
      if (!name) return arg.dayNumberText;
      return { html: `<span class="fc-daynum">${arg.dayNumberText}</span><span class="fc-holiday-label">${name}</span>` };
    },
    dayHeaderClassNames: function (arg) {
      return KR_HOLIDAYS[toDateStr(arg.date)] ? ["fc-holiday"] : [];
    },
    dayHeaderContent: function (arg) {
      const name = KR_HOLIDAYS[toDateStr(arg.date)];
      if (!name) return arg.text;
      return { html: `<span class="fc-daynum">${arg.text}</span><span class="fc-holiday-label">${name}</span>` };
    },
    events: "/api/events",
    eventDataTransform: function (raw) {
      if (raw.extendedProps) {
        raw.startEditable = raw.extendedProps.status === "요청" || raw.extendedProps.status === "확정";
        raw.durationEditable = false;
      }
      return raw;
    },
    eventClassNames: function (arg) {
      const classes = arg.event.extendedProps.status === "요청" ? ["ev-pending"] : [];
      if (arg.event.extendedProps.event_type === "상담") classes.push("ev-consult");
      if (selectedMemberId && String(arg.event.extendedProps.member_id) !== selectedMemberId) {
        classes.push("ev-dimmed");
      }
      return classes;
    },
    dateClick: function (info) {
      openCreateModal(info.dateStr);
    },
    eventDragStart: function (info) {
      if (info.event.extendedProps.status !== "요청") return;
      const roundId = info.event.extendedProps.round_id;
      const memberId = info.event.extendedProps.member_id;
      if (!roundId) return;
      showCalendarFlash("");
      fetch(`/rounds/${roundId}/members/${memberId}/valid-slots?exclude_event_id=${info.event.id}`)
        .then((r) => r.json())
        .then((slots) => {
          if (slots.length === 0) {
            showCalendarFlash("이 회원은 이번 회차 기간에 옮길 수 있는 다른 시간이 없어요. (이미 다른 예약이 그 회원의 가능한 요일을 모두 채웠어요)");
            return;
          }
          calendar.addEventSource({ id: DRAG_AVAILABILITY_SOURCE_ID, events: slots });
        });
    },
    eventDragStop: function () {
      const src = calendar.getEventSourceById(DRAG_AVAILABILITY_SOURCE_ID);
      if (src) src.remove();
    },
    eventDrop: function (info) {
      const start = info.event.start;
      const end = info.event.end;
      function toDate(d) {
        return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
      }
      function toTime(d) {
        return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
      }

      if (info.event.extendedProps.status === "확정") {
        if (!confirm("변경하시겠습니까?")) {
          info.revert();
          return;
        }
        fetch(`/api/events/${info.event.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
          body: JSON.stringify({
            date: toDate(start),
            start_time: toTime(start),
            end_time: toTime(end),
          }),
        }).then((res) => {
          if (!res.ok) {
            res.json().then((data) => alert(data.error || "변경하지 못했어요."));
            info.revert();
          }
        });
        return;
      }

      const roundId = info.event.extendedProps.round_id;
      if (!roundId) { info.revert(); return; }
      const slot = `${toDate(start)}|${toTime(start)}|${toTime(end)}`;

      const formData = new FormData();
      formData.set("csrf_token", csrfToken);
      formData.set("slot", slot);

      fetch(`/rounds/${roundId}/events/${info.event.id}/reassign`, {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: formData,
      })
        .then((r) => r.json())
        .then((data) => {
          showCalendarFlash(data.message);
          const eventsSection = document.getElementById("events-section");
          if (data.table_html && eventsSection) eventsSection.innerHTML = data.table_html;
          if (!data.ok) info.revert();
        });
    },
    eventClick: function (info) {
      const event = info.event;
      idField.value = event.id;
      typeField.value = event.extendedProps.event_type || "PT";
      if (typeField.value === "상담") {
        prospectNameField.value = event.extendedProps.member_name || "";
      } else {
        memberField.value = event.extendedProps.member_id;
      }
      toggleMemberFields();
      locationField.value = event.extendedProps.location_id || "";
      dateField.value = event.startStr.slice(0, 10);
      startField.value = event.startStr.slice(11, 16);
      endField.value = addMinutes(startField.value, durationForType());
      statusField.value = event.extendedProps.status;
      memoField.value = event.extendedProps.memo;
      document.querySelectorAll(".time-cube").forEach(function (cube) {
        cube.classList.toggle("selected", cube.dataset.time === startField.value);
      });

      if (event.extendedProps.status === "요청") {
        modalTitle.textContent = "예약 요청 확인";
        normalActions.classList.add("hidden");
        requestActions.classList.remove("hidden");
        statusFieldWrap.classList.add("hidden");
      } else {
        modalTitle.textContent = "일정 수정";
        normalActions.classList.remove("hidden");
        requestActions.classList.add("hidden");
        statusFieldWrap.classList.remove("hidden");
        deleteBtn.classList.remove("hidden");
      }
      openModal();
    },
  });
  calendar.render();
  window.ptCalendar = calendar;

  document.getElementById("member-filter").addEventListener("change", function () {
    selectedMemberId = this.value || "";

    // eventClassNames는 selectedMemberId 같은 외부 상태가 바뀌었다고 자동으로 다시 안 그려지므로,
    // 이벤트 소스를 통째로 내렸다가 다시 붙여서 강제로 전부 새로 그리게 한다.
    calendar.removeAllEventSources();
    calendar.addEventSource("/api/events");
    if (selectedMemberId) {
      calendar.addEventSource({
        id: AVAILABILITY_SOURCE_ID,
        url: `/api/members/${selectedMemberId}/available`,
      });
    }
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    const payload = {
      member_id: memberField.value,
      prospect_name: prospectNameField.value,
      location_id: locationField.value || null,
      date: dateField.value,
      start_time: startField.value,
      end_time: endField.value,
      status: statusField.value,
      memo: memoField.value,
      event_type: typeField.value,
    };
    const id = idField.value;
    const url = id ? `/api/events/${id}` : "/api/events";
    const method = id ? "PUT" : "POST";

    fetch(url, {
      method: method,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify(payload),
    }).then((res) => {
      if (res.ok) {
        calendar.refetchEvents();
        closeModal();
      } else {
        res.json().then((data) => alert(data.error || "저장하지 못했어요. 다시 시도해주세요."));
      }
    });
  });

  deleteBtn.addEventListener("click", function () {
    const id = idField.value;
    if (!id || !confirm("이 일정을 삭제할까요?")) return;
    fetch(`/api/events/${id}`, {
      method: "DELETE",
      headers: { "X-CSRFToken": csrfToken },
    }).then((res) => {
      if (res.ok) {
        calendar.refetchEvents();
        closeModal();
      }
    });
  });

  approveBtn.addEventListener("click", function () {
    const id = idField.value;
    fetch(`/api/events/${id}/approve`, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
    }).then((res) => {
      if (res.ok) {
        calendar.refetchEvents();
        closeModal();
      }
    });
  });

  rejectBtn.addEventListener("click", function () {
    const id = idField.value;
    if (!confirm("이 요청을 거절할까요?")) return;
    fetch(`/api/events/${id}`, {
      method: "DELETE",
      headers: { "X-CSRFToken": csrfToken },
    }).then((res) => {
      if (res.ok) {
        calendar.refetchEvents();
        closeModal();
      }
    });
  });

  const newRoundForm = document.getElementById("new-round-form");
  if (newRoundForm) {
    const nrStart = document.getElementById("new-round-start");
    const nrEnd = document.getElementById("new-round-end");

    function toIsoDate(d) {
      return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
    }
    function nextMonday() {
      const d = new Date();
      const day = d.getDay();
      let diff = (1 - day + 7) % 7;
      if (diff === 0) diff = 7;
      d.setDate(d.getDate() + diff);
      return d;
    }
    const defaultStart = nextMonday();
    const defaultEnd = new Date(defaultStart);
    defaultEnd.setDate(defaultStart.getDate() + 6);
    nrStart.value = toIsoDate(defaultStart);
    nrEnd.value = toIsoDate(defaultEnd);
    nrStart.addEventListener("change", function () {
      nrEnd.min = nrStart.value;
      if (nrEnd.value < nrStart.value) nrEnd.value = nrStart.value;
    });

    newRoundForm.addEventListener("submit", function (e) {
      e.preventDefault();
      if (nrEnd.value < nrStart.value) {
        alert("종료일이 시작일보다 빠를 수 없어요.");
        return;
      }
      fetch(newRoundForm.action, {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: new FormData(newRoundForm),
      })
        .then((r) => r.json())
        .then((data) => {
          if (data.ok) {
            window.location.reload();
          } else {
            alert(data.message || "회차를 시작하지 못했어요.");
          }
        });
    });
  }
});
