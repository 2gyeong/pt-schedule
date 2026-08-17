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

  function openCreateModal(dateStr, startTime) {
    modalTitle.textContent = "일정 등록";
    editOriginalDateTime = null;
    idField.value = "";
    typeField.value = "PT";
    prospectNameField.value = "";
    toggleMemberFields();
    locationField.value = "";
    dateField.value = dateStr;
    setStartTime(startTime || "10:00");
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
  let editOriginalDateTime = null;
  const AVAILABILITY_SOURCE_ID = "member-availability";
  const DRAG_AVAILABILITY_SOURCE_ID = "drag-availability";

  function showCalendarFlash(message) {
    const flash = document.getElementById("reassign-flash");
    if (!flash) return;
    flash.innerHTML = message ? `<ul class="flash"><li>${message}</li></ul>` : "";
  }

  let bannerTimeout = null;
  function showBanner(type, message) {
    const banner = document.getElementById("pt-banner");
    if (!banner) return;
    clearTimeout(bannerTimeout);
    banner.textContent = message;
    banner.className = `inline-banner ${type}`;
    bannerTimeout = setTimeout(function () {
      banner.className = "inline-banner hidden";
    }, 4000);
  }
  window.showBanner = showBanner;

  const holidaysEl = document.getElementById("kr-holidays");
  const KR_HOLIDAYS = holidaysEl ? JSON.parse(holidaysEl.textContent) : {};

  function toDateStr(d) {
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  function updateWeekLabel(info) {
    const titleEl = document.querySelector("#calendar .fc-toolbar-title");
    if (!titleEl) return;
    let labelEl = document.getElementById("calendar-week-label");
    if (info.view.type !== "timeGridWeek") {
      if (labelEl) labelEl.remove();
      return;
    }
    const sunday = info.start;
    const month = sunday.getMonth() + 1;
    const week = Math.floor((sunday.getDate() - 1) / 7) + 1;
    if (!labelEl) {
      labelEl = document.createElement("div");
      labelEl.id = "calendar-week-label";
      titleEl.parentNode.insertBefore(labelEl, titleEl);
    }
    labelEl.textContent = `${month}월 ${week}주차`;
  }

  function formatEventTime(date) {
    return String(date.getHours()).padStart(2, "0") + ":" + String(date.getMinutes()).padStart(2, "0");
  }

  function handleUnassignedDrop(info) {
    const el = info.draggedEl;
    const memberId = el.dataset.memberId;
    const roundId = calendarEl.dataset.roundId;
    clearMemberAvailabilityHighlight();
    if (!roundId || !info.date) return;
    const dateStr = toDateStr(info.date);
    const startStr = formatEventTime(info.date);
    const endStr = addMinutes(startStr, 50);

    function submit(confirmed) {
      fetch("/api/events", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        body: JSON.stringify({
          member_id: memberId,
          location_id: null,
          date: dateStr,
          start_time: startStr,
          end_time: endStr,
          event_type: "PT",
          round_id: roundId,
          confirmed_outside_availability: confirmed,
        }),
      })
        .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
        .then(({ ok, data }) => {
          if (data.needs_confirmation) {
            if (confirm(data.message)) {
              submit(true);
              return;
            }
            showBanner("error", data.message);
            return;
          }
          if (!ok) {
            showBanner("error", data.error || "등록하지 못했어요.");
            return;
          }
          calendar.refetchEvents();
          decrementUnassignedBlock(memberId);
          showBanner("success", "등록되었습니다.");
        })
        .catch(function () {
          showBanner("error", "등록하지 못했어요. 다시 시도해주세요.");
        });
    }
    submit(false);
  }

  const UNASSIGNED_AVAILABILITY_SOURCE_ID = "unassigned-drag-availability";

  function clearMemberAvailabilityHighlight() {
    const src = calendar.getEventSourceById(UNASSIGNED_AVAILABILITY_SOURCE_ID);
    if (src) src.remove();
  }

  function showMemberAvailabilityHighlight(memberId) {
    if (!memberId) return;
    const view = calendar.view;
    const start = toDateStr(view.activeStart);
    const end = toDateStr(view.activeEnd);
    fetch(`/api/members/${memberId}/available?start=${start}&end=${end}`)
      .then((r) => r.json())
      .then((slots) => {
        clearMemberAvailabilityHighlight();
        const yellow = slots.map(function (s) {
          return Object.assign({}, s, { color: "#f0cf5a" });
        });
        calendar.addEventSource({ id: UNASSIGNED_AVAILABILITY_SOURCE_ID, events: yellow });
      });
  }

  function wireUnassignedDragHighlight() {
    const list = document.getElementById("unassigned-list");
    if (!list) return;
    list.querySelectorAll(".unassigned-block").forEach(function (block) {
      if (block.dataset.highlightWired) return;
      block.dataset.highlightWired = "1";
      block.addEventListener("mousedown", function () {
        showMemberAvailabilityHighlight(block.dataset.memberId);
      });
      block.addEventListener("touchstart", function () {
        showMemberAvailabilityHighlight(block.dataset.memberId);
      }, { passive: true });
    });
  }
  document.addEventListener("mouseup", clearMemberAvailabilityHighlight);
  document.addEventListener("touchend", clearMemberAvailabilityHighlight);

  function ensureUnassignedPanel() {
    let panel = document.getElementById("unassigned-panel");
    if (panel) return panel;
    const layout = document.querySelector(".calendar-layout");
    if (!layout) return null;
    panel = document.createElement("aside");
    panel.id = "unassigned-panel";
    panel.dataset.roundId = calendarEl.dataset.roundId || "";
    panel.innerHTML =
      '<h3>미배정</h3>' +
      '<p class="hint">이번 회차에 아직 못 넣은 회원이에요. 달력으로 끌어다 놓으면 그 시간에 바로 등록돼요.</p>' +
      '<div id="unassigned-list"></div>';
    layout.appendChild(panel);
    new FullCalendar.Interaction.Draggable(document.getElementById("unassigned-list"), {
      itemSelector: ".unassigned-block",
    });
    return panel;
  }

  function addToUnassignedPanel(memberId, memberName) {
    const panel = ensureUnassignedPanel();
    if (!panel) return;
    const list = document.getElementById("unassigned-list");
    let block = list.querySelector(`.unassigned-block[data-member-id="${memberId}"]`);
    if (block) {
      const missing = Number(block.dataset.missing) + 1;
      block.dataset.missing = String(missing);
      block.querySelector(".unassigned-count").textContent = `${missing}회`;
    } else {
      block = document.createElement("div");
      block.className = "unassigned-block";
      block.dataset.memberId = memberId;
      block.dataset.name = memberName;
      block.dataset.missing = "1";
      block.innerHTML =
        `<span class="unassigned-name">${memberName}</span><span class="unassigned-count">1회</span>`;
      list.appendChild(block);
    }
    refreshUnassignedEmptyHint();
    wireUnassignedDragHighlight();
  }

  const calendarEl = document.getElementById("calendar");
  const calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: "timeGridWeek",
    initialDate: roundStartDate || undefined,
    locale: "ko",
    hiddenDays: [0],
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
    droppable: true,
    drop: handleUnassignedDrop,
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
      if (arg.event.display === "background") return [];
      const classes = arg.event.extendedProps.status === "요청" ? ["ev-pending"] : [];
      if (arg.event.extendedProps.event_type === "상담") classes.push("ev-consult");
      if (selectedMemberId && String(arg.event.extendedProps.member_id) !== selectedMemberId) {
        classes.push("ev-dimmed");
      }
      return classes;
    },
    dateClick: function (info) {
      if (info.view.type === "dayGridMonth") {
        openCreateModal(toDateStr(info.date));
      } else {
        openCreateModal(toDateStr(info.date), formatEventTime(info.date));
      }
    },
    eventDragStart: function (info) {
      // 어떤 상태의 일정을 드래그하든(확정/요청 상관없이) 그 회원의 가능 시간을 노란색으로 보여준다.
      if (info.event.extendedProps.event_type === "PT" && info.event.extendedProps.member_id) {
        showMemberAvailabilityHighlight(info.event.extendedProps.member_id);
      }

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
    eventDragStop: function (info) {
      const src = calendar.getEventSourceById(DRAG_AVAILABILITY_SOURCE_ID);
      if (src) src.remove();
      clearMemberAvailabilityHighlight();

      // 배정된 일정을 달력 밖 "미배정" 패널 위에 놓으면 다시 미배정으로 되돌린다 (양방향 드래그).
      const panel = document.getElementById("unassigned-panel");
      if (!panel || !info.event.extendedProps.round_id || !info.jsEvent) return;
      const rect = panel.getBoundingClientRect();
      const x = info.jsEvent.clientX;
      const y = info.jsEvent.clientY;
      const overPanel = x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
      if (!overPanel) return;

      const memberId = info.event.extendedProps.member_id;
      const memberName = info.event.extendedProps.member_name;
      if (!confirm(`${memberName}님을 다시 미배정으로 되돌릴까요?`)) return;
      fetch(`/api/events/${info.event.id}`, {
        method: "DELETE",
        headers: { "X-CSRFToken": csrfToken },
      }).then((res) => {
        if (res.ok) {
          info.event.remove();
          addToUnassignedPanel(memberId, memberName);
          showBanner("success", "미배정으로 옮겼습니다.");
        } else {
          showBanner("error", "되돌리지 못했어요.");
        }
      });
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
        function submitMove(confirmed) {
          fetch(`/api/events/${info.event.id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
            body: JSON.stringify({
              date: toDate(start),
              start_time: toTime(start),
              end_time: toTime(end),
              check_availability: true,
              confirmed_outside_availability: confirmed,
            }),
          })
            .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
            .then(({ ok, data }) => {
              if (data.needs_confirmation) {
                if (confirm(data.message)) {
                  submitMove(true);
                  return;
                }
                showBanner("error", data.message);
                info.revert();
                return;
              }
              if (!ok) {
                showBanner("error", data.error || "변경하지 못했어요.");
                info.revert();
                return;
              }
              showBanner("success", "저장되었습니다.");
            });
        }
        submitMove(false);
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
      editOriginalDateTime = { date: dateField.value, start: startField.value };
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

  function refreshUnassignedEmptyHint() {
    const panel = document.getElementById("unassigned-panel");
    const list = document.getElementById("unassigned-list");
    if (!panel || !list) return;
    let hint = document.getElementById("unassigned-empty-hint");
    if (!list.children.length) {
      if (!hint) {
        hint = document.createElement("p");
        hint.className = "hint";
        hint.id = "unassigned-empty-hint";
        hint.textContent = "모두 배정됐어요.";
        panel.appendChild(hint);
      }
    } else if (hint) {
      hint.remove();
    }
  }

  function decrementUnassignedBlock(memberId) {
    const block = document.querySelector(`.unassigned-block[data-member-id="${memberId}"]`);
    if (!block) return;
    const remaining = Number(block.dataset.missing) - 1;
    if (remaining <= 0) {
      block.remove();
    } else {
      block.dataset.missing = String(remaining);
      block.querySelector(".unassigned-count").textContent = `${remaining}회`;
    }
    refreshUnassignedEmptyHint();
  }

  const unassignedListEl = document.getElementById("unassigned-list");
  if (unassignedListEl) {
    new FullCalendar.Interaction.Draggable(unassignedListEl, { itemSelector: ".unassigned-block" });
    wireUnassignedDragHighlight();
  }

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
    const id = idField.value;
    const url = id ? `/api/events/${id}` : "/api/events";
    const method = id ? "PUT" : "POST";
    // 날짜/시간을 실제로 바꿀 때만(또는 새로 만들 때만) 회원 가능 시간을 확인한다.
    // 메모/상태 등 다른 값만 바꾸는 저장까지 매번 되물으면 번거로우니 제외.
    const timeChanged =
      !editOriginalDateTime ||
      dateField.value !== editOriginalDateTime.date ||
      startField.value !== editOriginalDateTime.start;

    function submitForm(confirmed) {
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
        check_availability: timeChanged,
        confirmed_outside_availability: confirmed,
      };
      fetch(url, {
        method: method,
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify(payload),
      })
        .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
        .then(({ ok, data }) => {
          if (data.needs_confirmation) {
            if (confirm(data.message)) {
              submitForm(true);
              return;
            }
            showBanner("error", data.message);
            return;
          }
          if (!ok) {
            showBanner("error", data.error || "저장하지 못했어요. 다시 시도해주세요.");
            return;
          }
          calendar.refetchEvents();
          closeModal();
          showBanner("success", id ? "저장되었습니다." : "등록되었습니다.");
        });
    }
    submitForm(false);
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

    function shiftIsoDate(iso, days) {
      const d = new Date(iso + "T00:00:00");
      d.setDate(d.getDate() + days);
      return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
    }
    function shiftNewRoundWeek(days) {
      nrStart.value = shiftIsoDate(nrStart.value, days);
      nrEnd.min = nrStart.value;
      nrEnd.value = shiftIsoDate(nrEnd.value, days);
    }
    const nrPrevBtn = document.getElementById("new-round-prev-week");
    const nrNextBtn = document.getElementById("new-round-next-week");
    if (nrPrevBtn) nrPrevBtn.addEventListener("click", function () { shiftNewRoundWeek(-7); });
    if (nrNextBtn) nrNextBtn.addEventListener("click", function () { shiftNewRoundWeek(7); });

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
