import {AfterViewInit, Component, ElementRef, OnInit, ViewChild} from '@angular/core';
import {faCheckCircle, faTimesCircle, faTrashAlt} from '@fortawesome/free-regular-svg-icons';
import {faDownload, faExternalLinkAlt, faMoon, faRedoAlt, faSun, faBan} from '@fortawesome/free-solid-svg-icons';
import {CookieService} from 'ngx-cookie-service';
import {map, Observable} from 'rxjs';

import {DownloadsService, MAP} from './downloads.service';
import {ParentCheckboxComponent} from './parent-checkbox.component';
import {Format, Formats} from './types/formats';
import {Download} from './types/download';
import {Status} from './types/status';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.sass'],
})
export class AppComponent implements OnInit, AfterViewInit {
  addUrl: string;
  formats: Format[] = Formats;
  selectedQualityId: string;
  selectedFormat: Format;
  folder: string;
  customNamePrefix: string;
  addInProgress = false;
  darkMode: boolean;
  customDirs$: Observable<string[]>;

  @ViewChild('queueParentCheckbox') queueParentCheckbox: ParentCheckboxComponent;
  @ViewChild('queueDelSelected') queueDelSelected: ElementRef;
  @ViewChild('doneParentCheckbox') doneParentCheckbox: ParentCheckboxComponent;
  @ViewChild('doneDelSelected') doneDelSelected: ElementRef;
  @ViewChild('doneClearCompleted') doneClearCompleted: ElementRef;
  @ViewChild('doneClearFailed') doneClearFailed: ElementRef;

  faTrashAlt = faTrashAlt;
  faBan = faBan;
  faCheckCircle = faCheckCircle;
  faTimesCircle = faTimesCircle;
  faRedoAlt = faRedoAlt;
  faSun = faSun;
  faMoon = faMoon;
  faDownload = faDownload;
  faExternalLinkAlt = faExternalLinkAlt;

  constructor(public downloads: DownloadsService, private cookieService: CookieService) {
    const selectedFormatId = cookieService.get('metube_format') || 'any';
    this.selectedFormat = this.formats.find(format => format.id === selectedFormatId);
    this.selectedQualityId = cookieService.get('metube_quality') || 'best';
    this.setupTheme(cookieService);
  }

  ngOnInit(): void {
    this.customDirs$ = this.getMatchingCustomDir();
  }

  ngAfterViewInit(): void {
    this.downloads.queueChanged.subscribe(() => {
      this.queueParentCheckbox.selectionChanged();
    });
    this.downloads.doneChanged.subscribe(() => {
      this.doneParentCheckbox.selectionChanged();
      const downloadsDone = [...this.downloads.done.values()];
      const hasAnyCompleted = downloadsDone.some(dl => dl.status === 'finished');
      const hasAnyFailed = downloadsDone.some(dl => dl.status === 'error');
      this.doneClearCompleted.nativeElement.disabled = !hasAnyCompleted;
      this.doneClearFailed.nativeElement.disabled = !hasAnyFailed;
    });
  }

  // workaround to allow fetching of Map values in the order they were inserted
  //  https://github.com/angular/angular/issues/31420
  asIsOrder(a, b): number {
    return 1;
  }

  showAdvanced(): boolean {
    return this.downloads.configuration?.CUSTOM_DIRS;
  }

  allowCustomDir(tag: string): string | boolean {
    return this.downloads.configuration?.CREATE_CUSTOM_DIRS ? tag : false;
  }

  isAudioType(): boolean {
    return this.selectedFormat.isAudioOnly || this.selectedQualityId === 'audio';
  }

  getMatchingCustomDir(): Observable<string[]> {
    return this.downloads.customDirsChanged.asObservable().pipe(map((output) => {
      // Keep logic consistent with app/ytdl.py
      if (this.isAudioType()) {
        console.debug('Showing audio-specific download directories');
        return output.audio_download_dir;
      } else {
        console.debug('Showing default download directories');
        return output.download_dir;
      }
    }));
  }

  setupTheme(cookieService: CookieService): void {
    if (cookieService.check('metube_dark')) {
      this.darkMode = cookieService.get('metube_dark') === 'true';
    } else {
      this.darkMode = window.matchMedia('prefers-color-scheme: dark').matches;
    }
    this.setTheme();
  }

  themeChanged(): void {
    this.darkMode = !this.darkMode;
    this.cookieService.set('metube_dark', this.darkMode.toString(), {expires: 3650});
    this.setTheme();
  }

  setTheme(): void {
    const doc = document.querySelector('html');
    const filter = this.darkMode ? 'invert(1) hue-rotate(180deg)' : '';
    doc.style.filter = filter;
  }

  formatChanged(): void {
    const hasSelectedQuality = this.selectedFormat.qualities.find(quality => quality.id === this.selectedQualityId);
    if (!hasSelectedQuality) {
      this.selectedQualityId = 'best';
      this.qualityChanged();
    }
    this.cookieService.set('metube_format', this.selectedFormat.id, {expires: 3650});
    // Re-trigger custom directory change
    this.downloads.customDirsChanged.next(this.downloads.customDirs);
  }

  qualityChanged(): void {
    this.cookieService.set('metube_quality', this.selectedQualityId, {expires: 3650});
    // Re-trigger custom directory change
    this.downloads.customDirsChanged.next(this.downloads.customDirs);
  }

  queueSelectionChanged(checked: number): void {
    this.queueDelSelected.nativeElement.disabled = checked === 0;
  }

  doneSelectionChanged(checked: number): void {
    this.doneDelSelected.nativeElement.disabled = checked === 0;
  }

  addCurrentDownload(): void {
    const download = {
      url: this.addUrl,
      quality: this.selectedQualityId,
      format: this.selectedFormat.id,
      folder: this.folder,
      customNamePrefix: this.customNamePrefix
    };
    // TODO: separate Download and QueueDownload type?
    this.addDownload(download as unknown as Download);
  }

  addDownload(download: Download): void {
    console.debug('Downloading:', download);
    this.addInProgress = true;
    this.downloads.add(download).subscribe((status: Status) => {
      if (status.status === 'error') {
        alert(`Error adding URL: ${status.msg}`);
      } else {
        this.addUrl = '';
      }
      this.addInProgress = false;
    });
  }

  retryDownload(key: string, download: Download): void {
    this.delDownload('done', key);
    this.addDownload(download);
  }

  delDownload(where: MAP, id: string): void {
    this.downloads.delById(where, [id]).subscribe();
  }

  delSelectedDownloads(where: MAP): void {
    this.downloads.delByFilter(where, dl => dl.isChecked).subscribe();
  }

  clearCompletedDownloads(): void {
    this.downloads.delByFilter('done', dl => dl.status === 'finished').subscribe();
  }

  clearFailedDownloads(): void {
    this.downloads.delByFilter('done', dl => dl.status === 'error').subscribe();
  }

  buildDownloadLink(download: Download): string {
    // FIXME: missing checks for audio?
    const isAudio = download.quality === 'audio' || download.filename.endsWith('.mp3');
    let baseDir = isAudio ? 'audio_download/' : 'download/';

    if (download.folder) {
      baseDir += download.folder + '/';
    }

    return baseDir + encodeURIComponent(download.filename);
  }
}
