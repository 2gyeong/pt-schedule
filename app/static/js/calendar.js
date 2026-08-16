document.addEventListener("DOMContentLoaded", function () {
  const csrfToken = document
    .querySelector('meta[name="csrf-token"]')
    .getAttribute("content");

  const scheduleStartHour = Number(document.getElementById("calendar").dataset.startHour || 6);
  const scheduleEndHour = Number(document.getElementById("calendar").dataset.endHour || 22);

  const modal = document.getElementById("event-modal");
  const form = document.getElementById("event-form");
  const modalTitle = document.getElementById("modal-title");
  const idField = document.getElementById("event-id");
  const memberField = document.getElementById("event-member");
  const locationField = document.getElementById("event-location");
  const dateField = document.getElementById("event-date");
  const startField = document.getElementById("event-start");
  const endField = document.getElementById("event-end");
  const statusField = document.getElementById("event-status");
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

  function setStartTime(time) {
    startField.value = time;
    endField.value = addMinutes(time, 60);
    document.querySelectorAll(".time-cube").forEach(function (cube) {
      cube.classList.toggle("selected", cube.dataset.time === time);
    });
  }
  startField.addEventListener("change", function () {
    if (startField.value) {
      endField.value = addMinutes(startField.value, 60);
      document.querySelectorAll(".time-cube").forEach(function (cube) {
        cube.classList.toggle("selected", cube.dataset.time === startField.value);
      });
    }
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
    locationField.value = "";
    dateField.value = dateStr;
    setStartTime("10:00");
    statusField.value = "확정";
    normalActions.classList.remove("hidden");
    requestActions.classList.add("hidden");
    deleteBtn.classList.add("hidden");
    openModal();
  }

  document.getElementById("new-event-btn").addEventListener("click", function () {
    openCreateModal(todayStr());
  });

  let selectedMemberId = "";
  const AVAILABILITY_SOURCE_ID = "member-availability";

  const calendarEl = document.getElementById("calendar");
  const calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: "dayGridMonth",
    headerToolbar: {
      left: "prev,next today",
      center: "title",
      right: "dayGridMonth,timeGridWeek",
    },
    slotMinTime: String(scheduleStartHour).padStart(2, "0") + ":00:00",
    slotMaxTime: String(scheduleEndHour).padStart(2, "0") + ":00:00",
    events: "/api/events",
    eventClassNames: function (arg) {
      const classes = arg.event.extendedProps.status === "요청" ? ["ev-pending"] : [];
      if (selectedMemberId && String(arg.event.extendedProps.member_id) !== selectedMemberId) {
        classes.push("ev-dimmed");
      }
      return classes;
    },
    dateClick: function (info) {
      openCreateModal(info.dateStr);
    },
    eventClick: function (info) {
      const event = info.event;
      idField.value = event.id;
      memberField.value = event.extendedProps.member_id;
      locationField.value = event.extendedProps.location_id || "";
      dateField.value = event.startStr.slice(0, 10);
      startField.value = event.startStr.slice(11, 16);
      endField.value = event.endStr.slice(11, 16);
      statusField.value = event.extendedProps.status;
      memoField.value = event.extendedProps.memo;
      document.querySelectorAll(".time-cube").forEach(function (cube) {
        cube.classList.toggle("selected", cube.dataset.time === startField.value);
      });

      if (event.extendedProps.status === "요청") {
        modalTitle.textContent = "예약 요청 확인";
        normalActions.classList.add("hidden");
        requestActions.classList.remove("hidden");
      } else {
        modalTitle.textContent = "일정 수정";
        normalActions.classList.remove("hidden");
        requestActions.classList.add("hidden");
        deleteBtn.classList.remove("hidden");
      }
      openModal();
    },
  });
  calendar.render();

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
      location_id: locationField.value || null,
      date: dateField.value,
      start_time: startField.value,
      end_time: endField.value,
      status: statusField.value,
      memo: memoField.value,
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
});
