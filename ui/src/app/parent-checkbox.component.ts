import {Component, ElementRef, EventEmitter, Input, Output, ViewChild} from '@angular/core';
import {Checkable} from './types/checkable';

@Component({
  selector: 'app-parent-checkbox',
  template: `
    <div class="form-check">
      <input #parentCheckbox
             (change)="clicked()"
             [(ngModel)]="selected"
             class="form-check-input"
             id="{{id}}-select-all"
             type="checkbox">
      <label class="form-check-label" for="{{id}}-select-all"></label>
    </div>`
})
export class ParentCheckboxComponent {
  @Input() id: string;
  @Input() list: Map<string, Checkable>;
  @Output() changed = new EventEmitter<number>();

  @ViewChild('parentCheckbox') parentCheckbox: ElementRef<HTMLInputElement>;
  selected: boolean;

  clicked(): void {
    this.list.forEach(item => item.isChecked = this.selected);
    this.selectionChanged();
  }

  selectionChanged(): void {
    if (!this.parentCheckbox) {
      return;
    }
    const numChecked = [...this.list.values()].filter(item => item.isChecked).length;
    this.selected = numChecked > 0 && numChecked === this.list.size;
    this.parentCheckbox.nativeElement.indeterminate = numChecked > 0 && numChecked < this.list.size;
    this.changed.emit(numChecked);
  }
}

@Component({
  selector: 'app-child-checkbox',
  template: `
    <div class="form-check">
      <input (change)="parent.selectionChanged()"
             [(ngModel)]="checkable.isChecked"
             class="form-check-input"
             id="{{parent.id}}-{{id}}-select"
             type="checkbox">
      <label class="form-check-label" for="{{parent.id}}-{{id}}-select"></label>
    </div>
  `
})
export class ChildCheckboxComponent {
  @Input() id: string;
  @Input() parent: ParentCheckboxComponent;
  @Input() checkable: Checkable;
}
