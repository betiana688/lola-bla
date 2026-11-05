document.querySelectorAll("[data-toggle-password]").forEach(function (button) {
  var inputs = button.getAttribute("data-toggle-password").split(" ")
    .map(function (id) { return document.getElementById(id); })
    .filter(Boolean);
  button.addEventListener("click", function () {
    var show = inputs.length > 0 && inputs[0].type === "password";
    inputs.forEach(function (input) { input.type = show ? "text" : "password"; });
    button.textContent = show ? "hide" : "show";
    button.setAttribute("aria-pressed", show ? "true" : "false");
  });
});
