import './globals.css'; import {Providers} from './providers';
export const metadata={title:'Omen',description:'Discover and track opportunities.'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body><Providers>{children}</Providers></body></html>}
