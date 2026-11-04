(function () {
  var box = document.getElementById("link-box");
  if (!box) { return; }
  var token = box.getAttribute("data-csrf");
  var timer = setInterval(check, 4000);
  function check() {
    fetch("/link/check", {
      method: "POST",
      body: new URLSearchParams({ csrf: token }),
      credentials: "same-origin"
    }).then(function (response) {
      if (response.status === 401) { clearInterval(timer); location.reload(); return null; }
      return response.json();
    }).then(function (data) {
      if (data && data.done) { clearInterval(timer); location.reload(); }
    }).catch(function () { /* try again at the next tick */ });
  }
})();
