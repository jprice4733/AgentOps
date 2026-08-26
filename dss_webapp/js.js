// Load the app SPA in a full-page iframe pointing at the FastAPI backend.
// getWebAppBackendUrl() is injected by the DSS webapp runtime.
var backendUrl = getWebAppBackendUrl('');
var ifrm = document.createElement('iframe');
ifrm.setAttribute('src', backendUrl);
ifrm.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;border:none;z-index:999999;';
document.getElementById('app-frame').appendChild(ifrm);
