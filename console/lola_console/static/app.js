document.querySelectorAll("[data-toggle-password]").forEach(function (button) {
  var inputs = button.getAttribute("data-toggle-password").split(" ")
    .map(function (id) { return document.getElementById(id); })
    .filter(Boolean);
  button.addEventListener("click", function () {
    var show = inputs.length > 0 && inputs[0].type === "password";
    inputs.forEach(function (input) { input.type = show ? "text" : "password"; });
    button.classList.toggle("on", show);
    button.setAttribute("aria-label", show ? "hide password" : "show password");
    button.setAttribute("aria-pressed", show ? "true" : "false");
  });
});

document.addEventListener("click", function (event) {
  document.querySelectorAll("details.menu[open]").forEach(function (menu) {
    if (!menu.contains(event.target)) { menu.removeAttribute("open"); }
  });
});
document.addEventListener("keydown", function (event) {
  if (event.key === "Escape") {
    document.querySelectorAll("details.menu[open]").forEach(function (menu) { menu.removeAttribute("open"); });
  }
});
