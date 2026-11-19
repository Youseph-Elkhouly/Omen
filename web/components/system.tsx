'use client';
import {motion} from 'framer-motion'; import {ReactNode} from 'react';
export function GlassCard({children,className='',...props}:{children:ReactNode,className?:string,[key:string]:any}){return <motion.article whileHover={{y:-3}} transition={{duration:.18}} className={`glass-card ${className}`} {...props}>{children}</motion.article>}
export function ScoreRing({score}:{score:number}){const color=score>=85?'#63e6c1':score>=70?'#a99bff':'#eabf75';return <div className="score-ring" style={{'--score':`${score*3.6}deg`,'--score-color':color} as React.CSSProperties}><span>{score}</span></div>}
export function Tag({children}:{children:ReactNode}){return <span className="tag">{children}</span>}
export function DeadlineBadge({date}:{date:string}){const days=Math.ceil((new Date(date).getTime()-Date.now())/86400000);return <span className={`deadline ${days<=3?'urgent':''}`}><i/>{days<0?'Closed':days===0?'Today':`${days}d left`}</span>}
export function Skeleton(){return <div className="skeleton"/>}
