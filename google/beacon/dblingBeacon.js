function sendPing(userInfo) {
    var user_email = userInfo["email"];
    console.log("Got the email: " + user_email);

    // TODO: Check if previous pings failed, add their data to this ping
    var now = new Date().toUTCString();

    var xmlHttp = new XMLHttpRequest();
    xmlHttp.onreadystatechange = function () {
        if (xmlHttp.readyState === 4)
            pingCallback(xmlHttp.status, now, user_email);
    };
    xmlHttp.open("GET", "http://example.com", true);
    xmlHttp.send(null);
}
function pingCallback(status, now_str, user_email) {
    // TODO: Check the response code. If status == 200, it went through.
    if (status !== 200) {
        // TODO: Data didn't go through. Store the data so we can try again later.
    }
}
function startPing() {
    chrome.storage.local.get("dbling_info", checkInfo);
}
function checkInfo(userInfo) {
    if (typeof chrome.runtime.lastError === "undefined" && typeof userInfo["dbling_info"] !== "undefined") {
        // Getting stored info was successful
        sendPing(userInfo["dbling_info"]);
    }
    else {
        // Need to retrieve the info, store it for next time
        chrome.identity.getProfileUserInfo(function (newInfo) {
            chrome.storage.local.set({"dbling_info": newInfo});
            sendPing(newInfo);
        });
    }
}
function initialize() {
    startPing();
    setInterval(function(){startPing()},60*1000);
}
window.addEventListener("load", initialize);
