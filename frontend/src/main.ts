import '@/style.css'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from '@/router'
import App from '@/App.vue'
import { APP_NAME } from '@/config'

document.title = APP_NAME || 'App'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
