import {Injectable} from '@angular/core';
import {HttpClient, HttpErrorResponse} from '@angular/common/http';
import {Observable, of, Subject} from 'rxjs';
import {catchError} from 'rxjs/operators';
import {MeTubeSocket} from './metube-socket';
import {Download} from './types/download';
import {Status} from './types/status';
import {Config} from './types/config';

export type MAP = 'queue' | 'done';

@Injectable({
  providedIn: 'root'
})
export class DownloadsService {
  loading = true;
  queue = new Map<string, Download>();
  done = new Map<string, Download>();
  queueChanged = new Subject();
  doneChanged = new Subject();
  configuration?: Config;

  customDirs: {download_dir: string[], audio_download_dir: string[]};
  customDirsChanged = new Subject<typeof this.customDirs>();

  constructor(private http: HttpClient, private socket: MeTubeSocket) {
    socket.fromEvent('all').subscribe((strdata: string) => {
      this.loading = false;
      const data: [[[string, Download]], [[string, Download]]] = JSON.parse(strdata);
      this.queue.clear();
      data[0].forEach(entry => this.queue.set(...entry));
      this.done.clear();
      data[1].forEach(entry => this.done.set(...entry));
      this.queueChanged.next(null);
      this.doneChanged.next(null);
    });
    socket.fromEvent('added').subscribe((strdata: string) => {
      const data: Download = JSON.parse(strdata);
      this.queue.set(data.url, data);
      this.queueChanged.next(null);
    });
    socket.fromEvent('updated').subscribe((strdata: string) => {
      const data: Download = JSON.parse(strdata);
      const dl: Download = this.queue.get(data.url);
      data.isChecked = dl.isChecked;
      data.deleting = dl.deleting;
      this.queue.set(data.url, data);
    });
    socket.fromEvent('completed').subscribe((strdata: string) => {
      const data: Download = JSON.parse(strdata);
      this.queue.delete(data.url);
      this.done.set(data.url, data);
      this.queueChanged.next(null);
      this.doneChanged.next(null);
    });
    socket.fromEvent('canceled').subscribe((strdata: string) => {
      const data: string = JSON.parse(strdata);
      this.queue.delete(data);
      this.queueChanged.next(null);
    });
    socket.fromEvent('cleared').subscribe((strdata: string) => {
      const data: string = JSON.parse(strdata);
      this.done.delete(data);
      this.doneChanged.next(null);
    });
    socket.fromEvent('configuration').subscribe((strdata: string) => {
      const data = JSON.parse(strdata);
      console.debug('got configuration:', data);
      this.configuration = data;
    });
    socket.fromEvent('custom_dirs').subscribe((strdata: string) => {
      const data = JSON.parse(strdata);
      console.debug('got custom_dirs:', data);
      this.customDirs = data;
      this.customDirsChanged.next(data);
    });
  }

  handleHTTPError(error: HttpErrorResponse): Observable<{ msg: any; status: 'error' }> {
    const msg = error.error instanceof ErrorEvent ? error.error.message : error.error;
    return of({status: 'error', msg});
  }

  public add(download: Download) {
    return this.http.post<Status>('add', download).pipe(catchError(this.handleHTTPError));
  }

  public delById(where: MAP, ids: string[]): Observable<any> {
    for (const id of ids) {
      this[where].get(id).deleting = true;
    }
    return this.http.post('delete', {where, ids});
  }

  public delByFilter(where: MAP, filter: (dl: Download) => boolean): Observable<any> {
    const ids: string[] = [...this[where].values()].filter(filter).map((dl: Download) => dl.url);
    return this.delById(where, ids);
  }
}
