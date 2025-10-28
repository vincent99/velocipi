/// <reference types="vite/client" />
/// <reference types="types/tire" />

declare module '*.vue' {
    import type {DefineComponent} from 'vue'
    const component: DefineComponent<{}, {}, any>
    export default component
}
