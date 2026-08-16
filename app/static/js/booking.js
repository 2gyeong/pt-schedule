document.addEventListener("DOMContentLoaded", function () {
  const csrfToken = document
    .querySelector('meta[name="csrf-token"]')
    .getAttribute("content");

  const calendarEl = document.getElementById("calendar");
  const token = calendarEl.dataset.token;

  const modal = document.getElementById("request-modal");
  const form = document.getElementById("request-form");
  const dateField = document.getElementById("req-date");
  const startField = document.getElementById("req-start");
  const endField = document.getElementById("req-end");
  const memoField = document.getElementById("req-memo");
  const cancelBtn = document.getElementById("req-cancel-btn");
  const successMsg = document.getElementById("request-success");

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

  const calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: "dayGridMonth",
    headerToolbar: {
      left: "prev,next today",
      center: "title",
      right: "dayGridMonth,timeGridWeek",
    },
    validRange: { start: todayStr() },
    events: `/book/${token}/busy`,
    dateClick: function (info) {
      dateField.value = info.dateStr;
      startField.value = "10:00";
      endField.value = "11:00";
      memoField.value = "";
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
      end_time: endField.value,
      memo: memoField.value,
    };
    fetch(`/book/${token}/request`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify(payload),
    }).then((res) => {
      if (res.ok) {
        form.classList.add("hidden");
        successMsg.classList.remove("hidden");
        calendar.refetchEvents();
        setTimeout(closeModal, 1800);
      }
    });
  });
});
