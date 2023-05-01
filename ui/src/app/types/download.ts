import {Checkable} from './checkable';

export type Download = {
  id: string;
  title: string;
  url: string;
  status: 'error' | 'finished' | 'preparing';
  msg: string;
  format: string;
  customNamePrefix: string;
  filename: string;
  folder: string;
  quality: string;
  percent: number;
  speed: number;
  eta: number;
  deleting?: boolean;
} & Checkable;
