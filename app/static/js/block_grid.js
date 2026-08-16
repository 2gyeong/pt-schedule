function initBlockGrid(container, options) {
  const days = ["월", "화", "수", "목", "금", "토", "일"];
  const hours = [];
  for (let h = 6; h <= 21; h++) hours.push(h);

  const existingSet = new Set((options.existing || []).map((b) => b.weekday + "-" + b.hour));
  const constraintSet = options.constraint
    ? new Set(options.constraint.map((b) => b.weekday + "-" + b.hour))
    : null;

  const grid = document.createElement("div");
  grid.className = "block-grid";

  grid.appendChild(document.createElement("div"));
  days.forEach(function (d) {
    const el = document.createElement("div");
    el.className = "block-grid-header";
    el.textContent = d;
    grid.appendChild(el);
  });

  let isPainting = false;
  let paintValue = true;

  function setCell(cell, value) {
    cell.classList.toggle("selected", value);
  }

  hours.forEach(function (h) {
    const label = document.createElement("div");
    label.className = "block-grid-hour-label";
    label.textContent = String(h).padStart(2, "0") + ":00";
    grid.appendChild(label);

    days.forEach(function (_, weekday) {
      const key = weekday + "-" + h;
      const allowed = !constraintSet || constraintSet.has(key);

      const cell = document.createElement("div");
      cell.className = "block-cell";
      cell.dataset.weekday = weekday;
      cell.dataset.hour = h;
      if (existingSet.has(key)) cell.classList.add("selected");
      if (!allowed) {
        cell.classList.add("disabled");
        if (cell.classList.contains("selected")) cell.classList.add("invalid");
      }

      if (allowed) {
        cell.addEventListener("mousedown", function (e) {
          e.preventDefault();
          isPainting = true;
          paintValue = !cell.classList.contains("selected");
          setCell(cell, paintValue);
        });
        cell.addEventListener("mouseenter", function () {
          if (isPainting) setCell(cell, paintValue);
        });
        cell.addEventListener("touchstart", function () {
          isPainting = true;
          paintValue = !cell.classList.contains("selected");
          setCell(cell, paintValue);
        }, { passive: true });
      }

      grid.appendChild(cell);
    });
  });

  grid.addEventListener("touchmove", function (e) {
    if (!isPainting) return;
    const touch = e.touches[0];
    const el = document.elementFromPoint(touch.clientX, touch.clientY);
    if (el && el.classList.contains("block-cell") && !el.classList.contains("disabled")) {
      setCell(el, paintValue);
    }
  }, { passive: true });

  document.addEventListener("mouseup", function () {
    isPainting = false;
  });
  document.addEventListener("touchend", function () {
    isPainting = false;
  });

  container.appendChild(grid);

  const actions = document.createElement("div");
  actions.className = "block-grid-actions";
  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.textContent = options.saveLabel || "저장";
  const status = document.createElement("span");
  status.className = "block-grid-status";
  actions.appendChild(saveBtn);
  actions.appendChild(status);
  container.appendChild(actions);

  saveBtn.addEventListener("click", function () {
    const blocks = [];
    grid.querySelectorAll(".block-cell.selected").forEach(function (cell) {
      blocks.push({ weekday: Number(cell.dataset.weekday), hour: Number(cell.dataset.hour) });
    });
    fetch(options.saveUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": options.csrfToken,
      },
      body: JSON.stringify({ blocks: blocks }),
    }).then(function (res) {
      if (res.ok && options.reloadOnSave) {
        alert("완료되었습니다.");
        window.location.reload();
        return;
      }
      status.textContent = res.ok ? "저장됨!" : "저장 실패";
      setTimeout(function () {
        status.textContent = "";
      }, 1800);
    });
  });
}
